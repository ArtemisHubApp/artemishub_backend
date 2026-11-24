import asyncio
import contextlib
import logging
import time
from dataclasses import replace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import InterfaceError, OperationalError

from artemis_backend.adapters.banco import criar_motor
from artemis_backend.main import criar_app
from tests.apoio.valores import SENHA_DE_TESTE

EMAIL = "qa4x@example.com"
MENSAGEM_503 = {"detail": "Serviço indisponível, tente de novo"}
MENSAGEM_500 = {"detail": "Erro interno"}


class ProxyCongelavel:
    """Fica entre a API e o Postgres. Congelado, aceita conexões e não repassa nenhum byte."""

    def __init__(self, host: str, porta: int) -> None:
        self._destino = (host, porta)
        self._livre = asyncio.Event()
        self._livre.set()
        self._tarefas: set[asyncio.Task] = set()

    def congelar(self) -> None:
        self._livre.clear()

    async def _repassar(self, leitor, escritor) -> None:
        while dados := await leitor.read(65536):
            await self._livre.wait()
            escritor.write(dados)
            await escritor.drain()

    async def _atender(self, leitor, escritor) -> None:
        tarefa = asyncio.current_task()
        self._tarefas.add(tarefa)
        saida = None
        try:
            await self._livre.wait()
            entrada, saida = await asyncio.open_connection(*self._destino)
            async with asyncio.TaskGroup() as grupo:
                grupo.create_task(self._repassar(leitor, saida))
                grupo.create_task(self._repassar(entrada, escritor))
        except (asyncio.CancelledError, ExceptionGroup, OSError):
            return
        finally:
            for fim in (escritor, saida):
                if fim is not None:
                    fim.close()
            self._tarefas.discard(tarefa)

    async def iniciar(self) -> int:
        self._servidor = await asyncio.start_server(self._atender, "127.0.0.1", 0)
        return self._servidor.sockets[0].getsockname()[1]

    async def parar(self) -> None:
        self._servidor.close()
        tarefas = list(self._tarefas)
        for tarefa in tarefas:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)


@pytest_asyncio.fixture
async def com_proxy(app, config):
    """Cliente de uma API que fala com o banco migrado por um proxy congelável."""
    url = make_url(app.state.config.database_url)
    proxy = ProxyCongelavel(url.host, url.port)
    porta = await proxy.iniciar()
    pelo_proxy = url.set(host="127.0.0.1", port=porta).render_as_string(hide_password=False)
    app_proxy = criar_app(replace(config, database_url=pelo_proxy))
    transporte = httpx.ASGITransport(app=app_proxy)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        yield c, proxy
    await proxy.parar()
    with contextlib.suppress(Exception):
        await app_proxy.state.motor.dispose()


async def logar(cliente) -> tuple[httpx.Response, float]:
    inicio = time.monotonic()
    async with asyncio.timeout(40):
        r = await cliente.post("/v1/auth/login", json={"email": EMAIL, "senha": SENHA_DE_TESTE})
    return r, time.monotonic() - inicio


def sem_vazamento(caplog) -> bool:
    return EMAIL not in caplog.text and "Traceback" not in caplog.text


async def test_banco_que_aceita_e_nao_responde_da_503_em_5_segundos(com_proxy, caplog):
    cliente, proxy = com_proxy
    proxy.congelar()
    caplog.set_level(logging.DEBUG)
    r, segundos = await logar(cliente)
    assert (r.status_code, r.json()) == (503, MENSAGEM_503)
    assert 4 < segundos < 30
    assert sem_vazamento(caplog)


async def test_banco_que_congela_com_conexao_aberta_da_503_sem_esperar_60s(com_proxy, caplog):
    cliente, proxy = com_proxy
    assert (await logar(cliente))[0].status_code == 401
    proxy.congelar()
    caplog.set_level(logging.DEBUG)
    r, segundos = await logar(cliente)
    assert (r.status_code, r.json()) == (503, MENSAGEM_503)
    assert segundos < 25
    assert sem_vazamento(caplog)


async def test_pool_esgotado_da_503(app, cliente, monkeypatch):
    monkeypatch.setattr(app.state.motor.pool, "_timeout", 0.2)
    async with contextlib.AsyncExitStack() as pilha:
        for _ in range(15):
            await pilha.enter_async_context(app.state.motor.connect())
        r, _ = await logar(cliente)
    assert (r.status_code, r.json()) == (503, MENSAGEM_503)


async def test_banco_inexistente_da_503(app, config):
    url = app.state.config.database_url.rsplit("/", 1)[0] + "/nao_existe"
    app_sem_banco = criar_app(replace(config, database_url=url))
    transporte = httpx.ASGITransport(app=app_sem_banco)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        r, _ = await logar(c)
    await app_sem_banco.state.motor.dispose()
    assert (r.status_code, r.json()) == (503, MENSAGEM_503)


async def test_programming_error_da_500_sem_vazar(app, cliente, caplog):
    @app.get("/_teste/sql")
    async def sql() -> None:
        async with app.state.motor.connect() as conexao:
            await conexao.execute(
                text("SELECT * FROM tabela_que_nao_existe WHERE e = :e"), {"e": EMAIL}
            )

    caplog.set_level(logging.INFO)
    r = await cliente.get("/_teste/sql")
    assert (r.status_code, r.json()) == (500, MENSAGEM_500)
    assert sem_vazamento(caplog)
    assert "ProgrammingError" in caplog.text and "tabela_que_nao_existe" not in caplog.text


def _durante(contexto: Exception, erro: Exception) -> Exception:
    erro.__context__ = contexto
    return erro


@pytest.mark.parametrize(
    "erro",
    [
        FileNotFoundError("arquivo de qa4x@example.com"),
        ConnectionResetError("outro serviço"),
        TimeoutError("outro serviço"),
        InterfaceError("SELECT 1", {}, Exception("uso errado da conexão")),
        OperationalError("SELECT 1", {}, Exception("x")),
        _durante(OSError("antes"), RuntimeError("depois")),
        _durante(InterfaceError("SELECT 1", {}, Exception("x")), RuntimeError("depois")),
    ],
    ids=lambda e: type(e).__name__ + ("-com-contexto" if e.__context__ else ""),
)
async def test_erro_que_nao_e_conexao_com_o_banco_da_500(app, cliente, caplog, erro):
    @app.get("/_teste/erro")
    async def quebra() -> None:
        raise erro

    caplog.set_level(logging.INFO)
    r = await cliente.get("/_teste/erro")
    assert (r.status_code, r.json()) == (500, MENSAGEM_500)
    assert sem_vazamento(caplog)


async def test_motor_tem_limites_de_espera(config):
    motor = criar_motor(config.database_url)
    assert motor.pool.timeout() == 5
    await motor.dispose()

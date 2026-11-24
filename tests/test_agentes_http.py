import asyncio
import copy
import json
import logging
import time
from pathlib import Path

import httpx
import jsonschema
import pytest

from artemis_backend.adapters.agentes_http import AgentesHttp
from artemis_backend.application.perguntar import AgentesIndisponiveis, RespostaAgentes
from artemis_backend.domain.conversa import Troca
from artemis_backend.main import criar_app
from tests.apoio.agentes import AgentesFake

RAIZ = Path(__file__).resolve().parent.parent
CONTRATO = json.loads((RAIZ / "contratos" / "responder.v1.schema.json").read_text("utf-8"))
TOKEN = "token-de-servico-de-teste"
URL = "http://agentes.invalid"
LEMBRANCA = {
    "salario": True,
    "direitos": False,
    "cbo_familia": "2124",
    "cbo_familia_nome": "Analistas de TI",
    "ocupacao": None,
    "uf": "SP",
}
VALIDA = {
    "resposta": "Olá\n",
    "aprovada": True,
    "bloqueada": False,
    "fora_de_escopo": False,
    "lembranca": LEMBRANCA,
    "trace_id": "t1",
    "passos": ["pesquisa"],
}


def com(**campos) -> dict:
    return {**copy.deepcopy(VALIDA), **campos}


def sem(campo: str) -> dict:
    return {k: v for k, v in VALIDA.items() if k != campo}


def com_lembranca(**campos) -> dict:
    return com(lembranca={**LEMBRANCA, **campos})


VALIDAS = [
    VALIDA,
    com(lembranca=None),
    com(passos=[]),
    com(aprovada=False, bloqueada=True, fora_de_escopo=True),
    com_lembranca(cbo_familia=None, cbo_familia_nome=None, uf=None, ocupacao="dev"),
    com(resposta="á" * 20_000),
    com(trace_id=""),
]
INVALIDAS = [
    *(sem(campo) for campo in VALIDA),
    com(extra=1),
    com(resposta=""),
    com(resposta=" \n\t "),
    com(resposta="a" * 20_001),
    com(resposta=None),
    com(resposta=1),
    com(resposta="a\x00b"),
    com(resposta="a\x00\n"),
    com(resposta="a\ud800b"),
    com(aprovada="true"),
    com(aprovada=1),
    com(bloqueada=0),
    com(fora_de_escopo=None),
    com(trace_id=None),
    com(trace_id="t\x00"),
    com(trace_id="x" * 201),
    com(passos=None),
    com(passos="a"),
    com(passos=[1]),
    com(passos=["\x00"]),
    com(passos=["\udfff"]),
    com(lembranca=[]),
    com(lembranca={}),
    com_lembranca(salario=1),
    com_lembranca(direitos=None),
    com_lembranca(extra=1),
    com_lembranca(uf=1),
    com_lembranca(uf="SPX"),
    com_lembranca(cbo_familia="1" * 21),
    com_lembranca(ocupacao="o" * 201),
    com_lembranca(ocupacao="\x00"),
    com_lembranca(cbo_familia_nome="\ud83d"),
    com_lembranca(cbo_familia_nome="n" * 201),
    [],
    None,
    "texto",
]


def devolve(corpo) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda _: httpx.Response(200, content=json.dumps(corpo).encode("ascii"))
    )


async def responder(transporte=None, url=URL, timeout=5.0, **kw) -> RespostaAgentes:
    agentes = AgentesHttp(url, TOKEN, timeout=timeout, transporte=transporte)
    argumentes = {"pergunta": "p", "sessao": "s", "historico": [], "lembranca": None, **kw}
    try:
        return await agentes.responder(**argumentes)
    finally:
        await agentes.fechar()


def _validador(nome: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{nome}", "$defs": CONTRATO["$defs"]},
    )


def test_contrato_e_um_schema_valido():
    jsonschema.Draft202012Validator.check_schema(CONTRATO)


@pytest.mark.parametrize("corpo", VALIDAS)
async def test_resposta_valida_passa_no_adaptador_e_no_contrato(corpo):
    assert _validador("resposta").is_valid(corpo)
    r = await responder(devolve(corpo))
    assert (r.resposta, r.lembranca, r.trace_id) == (
        corpo["resposta"],
        corpo["lembranca"],
        corpo["trace_id"],
    )
    assert (r.aprovada, r.bloqueada, r.fora_de_escopo) == (
        corpo["aprovada"],
        corpo["bloqueada"],
        corpo["fora_de_escopo"],
    )


@pytest.mark.parametrize("corpo", INVALIDAS, ids=range(len(INVALIDAS)))
async def test_resposta_fora_do_schema_falha_no_adaptador_e_no_contrato(corpo):
    assert not _validador("resposta").is_valid(corpo)
    with pytest.raises(AgentesIndisponiveis):
        await responder(devolve(corpo))


async def test_http_timeout_500_json_invalido_e_fora_do_schema():
    def estoura(pedido):
        raise httpx.ReadTimeout("lento", request=pedido)

    transportes = [
        httpx.MockTransport(estoura),
        httpx.MockTransport(lambda _: httpx.Response(500, json=VALIDA)),
        httpx.MockTransport(lambda _: httpx.Response(200, content=b"{")),
        devolve({"resposta": "oi"}),
    ]
    for transporte in transportes:
        with pytest.raises(AgentesIndisponiveis):
            await responder(transporte)


@pytest.mark.parametrize("status", [201, 204, 302, 400, 401, 404, 422, 503])
async def test_status_diferente_de_200_e_indisponivel(status):
    chamadas = []

    def atender(pedido):
        chamadas.append(pedido)
        return httpx.Response(status, json=VALIDA, headers={"Location": "http://outro.invalid/"})

    with pytest.raises(AgentesIndisponiveis):
        await responder(httpx.MockTransport(atender))
    assert len(chamadas) == 1  # nem redirecionamento nem nova tentativa


@pytest.mark.parametrize(
    "conteudo",
    [b"", b"\xff\xfe{}", b"[" * 100_000, b"<html>"],
    ids=["vazio", "nao-utf8", "muito-aninhado", "html"],
)
async def test_corpo_ilegivel_e_indisponivel(conteudo):
    with pytest.raises(AgentesIndisponiveis):
        await responder(httpx.MockTransport(lambda _: httpx.Response(200, content=conteudo)))


async def test_gzip_corrompido_e_indisponivel():
    def atender(_):
        return httpx.Response(200, content=b"nao-e-gzip", headers={"Content-Encoding": "gzip"})

    with pytest.raises(AgentesIndisponiveis):
        await responder(httpx.MockTransport(atender))


async def test_conexao_recusada_e_indisponivel(porta_fechada):
    with pytest.raises(AgentesIndisponiveis):
        await responder(url=f"http://127.0.0.1:{porta_fechada}")


async def test_http_manda_token_de_servico():
    pedidos = []

    def atender(pedido):
        pedidos.append(pedido)
        return httpx.Response(200, json=VALIDA)

    for url in (URL, URL + "/"):
        await responder(httpx.MockTransport(atender), url=url)
    for pedido in pedidos:
        assert pedido.headers["Authorization"] == f"Bearer {TOKEN}"
        assert (pedido.method, str(pedido.url)) == ("POST", f"{URL}/v1/responder")


async def test_pedido_segue_o_contrato():
    pedidos = []

    def atender(pedido):
        pedidos.append(json.loads(pedido.content))
        return httpx.Response(200, json=VALIDA)

    historico = [Troca("p1", "r1"), Troca("p2", "r2"), Troca("p3", "r3")]
    await responder(
        httpx.MockTransport(atender),
        pergunta="Olá?",
        sessao="id-da-conversa",
        historico=historico,
        lembranca=LEMBRANCA,
    )
    await responder(httpx.MockTransport(atender))
    assert pedidos[0] == {
        "pergunta": "Olá?",
        "sessao": "id-da-conversa",
        "historico": [
            {"pergunta": "p1", "resposta": "r1"},
            {"pergunta": "p2", "resposta": "r2"},
            {"pergunta": "p3", "resposta": "r3"},
        ],
        "lembranca": LEMBRANCA,
    }
    for pedido in pedidos:
        _validador("pedido").validate(pedido)


async def test_contrato_recusa_pedido_com_4_trocas_ou_campo_a_mais():
    troca = {"pergunta": "p", "resposta": "r"}
    pedido = {"pergunta": "p", "sessao": "s", "historico": [], "lembranca": None}
    assert _validador("pedido").is_valid(pedido)
    assert not _validador("pedido").is_valid({**pedido, "historico": [troca] * 4})
    assert not _validador("pedido").is_valid({**pedido, "email": "a@example.com"})


async def test_proxy_e_netrc_do_ambiente_sao_ignorados(monkeypatch, porta_fechada, tmp_path):
    netrc = tmp_path / "netrc"
    netrc.write_text("default login u password p\n")
    monkeypatch.setenv("NETRC", str(netrc))
    for variavel in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(variavel, f"http://127.0.0.1:{porta_fechada}")
    async with servidor(_resposta_http(VALIDA)) as url:
        assert (await responder(url=url)).resposta == VALIDA["resposta"]


class servidor:
    """Servidor TCP de verdade: manda cada pedaço com a pausa pedida."""

    def __init__(self, *pedacos: bytes, pausa: float = 0.0) -> None:
        self._pedacos, self._pausa = pedacos, pausa

    async def _atender(self, leitor, escritor) -> None:
        try:
            await leitor.readuntil(b"\r\n\r\n")
            for pedaco in self._pedacos:
                escritor.write(pedaco)
                await escritor.drain()
                await asyncio.sleep(self._pausa)
        except (ConnectionError, asyncio.CancelledError, asyncio.IncompleteReadError):
            return
        finally:
            escritor.close()

    async def __aenter__(self) -> str:
        self._servidor = await asyncio.start_server(self._atender, "127.0.0.1", 0)
        return f"http://127.0.0.1:{self._servidor.sockets[0].getsockname()[1]}"

    async def __aexit__(self, *_) -> None:
        self._servidor.close()


def _resposta_http(corpo) -> bytes:
    conteudo = json.dumps(corpo).encode()
    cabecalho = f"HTTP/1.1 200 OK\r\nContent-Length: {len(conteudo)}\r\nConnection: close\r\n\r\n"
    return cabecalho.encode() + conteudo


async def test_limite_de_tempo_e_total_mesmo_com_bytes_pingando():
    cabecalho = b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n"
    async with servidor(cabecalho, *[b" "] * 100, pausa=0.1) as url:
        inicio = time.monotonic()
        with pytest.raises(AgentesIndisponiveis):
            await responder(url=url, timeout=0.5)
    assert time.monotonic() - inicio < 2


def test_limite_padrao_e_60_segundos():
    assert AgentesHttp(URL, TOKEN)._timeout == 60.0


async def test_cancelamento_nao_vira_indisponivel():
    async with servidor(b"", pausa=30) as url:
        tarefa = asyncio.create_task(responder(url=url, timeout=20))
        await asyncio.sleep(0.1)
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa


async def test_logs_e_excecao_sem_corpo_nem_token(caplog):
    caplog.set_level(logging.DEBUG)
    async with servidor(_resposta_http(com(resposta="segredo-da-resposta"))) as url:
        await responder(url=url, pergunta="segredo-da-pergunta")
    with pytest.raises(AgentesIndisponiveis) as erro:
        await responder(devolve(com(resposta="segredo-da-resposta", extra=1)))
    texto = caplog.text + repr(erro.value) + str(erro.value.__cause__)
    assert erro.value.__suppress_context__
    assert "segredo" not in texto and TOKEN not in texto


async def test_app_fecha_o_cliente_http_ao_desligar(config):
    app = criar_app(config)
    async with app.router.lifespan_context(app):
        assert not app.state.agentes._cliente.is_closed
    assert app.state.agentes._cliente.is_closed
    await app.state.motor.dispose()


async def test_app_nao_fecha_agentes_que_recebeu_pronto(config):
    app = criar_app(config, AgentesFake())
    async with app.router.lifespan_context(app):
        pass  # AgentesFake não tem fechar(): não pode quebrar
    await app.state.motor.dispose()

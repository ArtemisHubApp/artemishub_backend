import uuid
from dataclasses import replace

import httpx
import pytest_asyncio

from artemis_backend.adapters.autenticacao import usuaria_atual
from artemis_backend.main import criar_app
from tests.apoio.sessao import (
    APAGADO,
    ATRIBUTOS,
    COOKIE,
    atributos_do_cookie,
    cadastrar,
    com_origem,
    em_cookie,
    logar,
)
from tests.apoio.valores import ANA, BIA, ORIGEM_DE_TESTE, TOKEN_INVALIDO


@pytest_asyncio.fixture
async def navegador(app):
    """Cliente https com o próprio pote de cookies, como o navegador."""
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url=ORIGEM_DE_TESTE) as c:
        yield c


async def test_login_grava_cookie_com_os_atributos(cliente):
    await cadastrar(cliente)
    r = await logar(cliente)
    assert r.status_code == 200
    assert set(r.json()) == {"token", "tipo"}
    assert atributos_do_cookie(r) == {
        **ATRIBUTOS,
        "valor": r.json()["token"],
        "max-age": "3600",
    }


async def test_cookie_sem_secure_so_muda_o_secure(config):
    local = replace(config, origem="http://localhost:5173", cookie_seguro=False)
    app = criar_app(local)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        r = await c.post("/v1/auth/sair", headers={"Cookie": f"{COOKIE}=x", "Origin": local.origem})
    await app.state.motor.dispose()
    assert r.status_code == 204
    assert atributos_do_cookie(r) == {k: v for k, v in APAGADO.items() if k != "secure"}


async def test_cadastro_e_login_errado_nao_gravam_cookie(cliente):
    assert "set-cookie" not in (await cadastrar(cliente)).headers
    corpo = {"email": ANA, "senha": "senha-errada"}
    r = await cliente.post("/v1/auth/login", json=corpo)
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


async def test_cookie_abre_as_rotas(cliente, entrar_como):
    await entrar_como(BIA)
    ana = em_cookie(await entrar_como(ANA))
    leitura = com_origem(ana, None)
    r = await cliente.get("/v1/conta", headers=leitura)
    assert r.status_code == 200
    assert set(r.json()) == {"id", "nome", "email"}
    assert r.json()["email"] == ANA
    assert (await cliente.get("/v1/conversas", headers=leitura)).status_code == 200
    assert (await cliente.post("/v1/conversas", headers=ana)).status_code == 201


async def test_conta_devolve_so_a_dona_do_token(cliente, entrar_como):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    da_ana = (await cliente.get("/v1/conta", headers=ana)).json()
    da_bia = (await cliente.get("/v1/conta", headers=bia)).json()
    assert (da_ana["email"], da_bia["email"]) == (ANA, BIA)
    assert da_ana["id"] != da_bia["id"]


async def test_jornada_no_navegador(navegador):
    origem = {"Origin": ORIGEM_DE_TESTE}
    assert (await cadastrar(navegador, **origem)).status_code == 201
    assert (await logar(navegador, **origem)).status_code == 200
    assert (await navegador.get("/v1/conta")).json()["email"] == ANA
    assert (await navegador.post("/v1/auth/sair", headers=origem)).status_code == 204
    assert (await navegador.get("/v1/conta")).status_code == 401


async def test_conta_que_some_depois_do_token_responde_401(app, cliente):
    app.dependency_overrides[usuaria_atual] = uuid.uuid4
    r = await cliente.get("/v1/conta")
    assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)

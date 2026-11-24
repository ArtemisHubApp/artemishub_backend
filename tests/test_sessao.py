import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from artemis_backend.adapters.banco import criar_fabrica_de_sessoes
from artemis_backend.adapters.rotas_auth import usuaria_atual
from artemis_backend.adapters.tabelas import Conversa, Usuaria
from artemis_backend.main import criar_app
from tests.conftest import ORIGEM_DE_TESTE, SENHA_DE_TESTE
from tests.test_auth import token
from tests.test_conta import em_cookie, rotas_protegidas

ANA = "ana@example.com"
BIA = "bia@example.com"
COOKIE = "artemis_sessao"
ORIGEM_NEGADA = {"detail": "Origem não permitida"}
TOKEN_INVALIDO = {"detail": "Token inválido ou vencido"}
ORIGENS_ERRADAS = [
    pytest.param(None, id="sem"),
    pytest.param("null", id="null"),
    pytest.param("", id="vazia"),
    pytest.param("https://outro.example.org", id="outro-site"),
    pytest.param("https://sub.artemis.example.com", id="subdominio"),
    pytest.param("https://example.com", id="dominio-pai"),
    pytest.param("https://artemis.example.com.outro.example.org", id="sufixo"),
    pytest.param("https://artemis.example.com:8443", id="outra-porta"),
    pytest.param("http://artemis.example.com", id="outro-esquema"),
    pytest.param("https://artemis.example.com/", id="barra"),
    pytest.param("https://ARTEMIS.example.com", id="maiusculas"),
]


@pytest_asyncio.fixture
async def sessao(app):
    async with criar_fabrica_de_sessoes(app.state.motor)() as s:
        yield s


@pytest_asyncio.fixture
async def navegador(app):
    """Cliente https com o próprio pote de cookies, como o navegador."""
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url=ORIGEM_DE_TESTE) as c:
        yield c


async def contar(sessao, tabela) -> int:
    return await sessao.scalar(select(func.count()).select_from(tabela))


def com_origem(cabecalhos: dict, origem: str | None) -> dict:
    sem_origem = {k: v for k, v in cabecalhos.items() if k != "Origin"}
    return sem_origem if origem is None else {**sem_origem, "Origin": origem}


async def logar(cliente, **cabecalhos) -> httpx.Response:
    corpo = {"email": ANA, "senha": SENHA_DE_TESTE}
    return await cliente.post("/v1/auth/login", json=corpo, headers=cabecalhos)


async def cadastrar(cliente, **cabecalhos) -> httpx.Response:
    corpo = {"email": ANA, "senha": SENHA_DE_TESTE, "consentimento": True}
    return await cliente.post("/v1/auth/cadastro", json=corpo, headers=cabecalhos)


def atributos_do_cookie(resposta) -> dict:
    [bruto] = resposta.headers.get_list("set-cookie")
    [(nome, cookie)] = SimpleCookie(bruto).items()
    assert nome == COOKIE
    return {
        "valor": cookie.value,
        **{k: v.lower() if isinstance(v, str) else v for k, v in cookie.items() if v},
    }


ATRIBUTOS = {"path": "/", "secure": True, "httponly": True, "samesite": "strict"}
APAGADO = {**ATRIBUTOS, "valor": "", "max-age": "0"}


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
    assert set(r.json()) == {"id", "email"}
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


@pytest.mark.parametrize("origem", ORIGENS_ERRADAS)
async def test_post_e_delete_com_cookie_exigem_origin(app, cliente, entrar_como, sessao, origem):
    ana = em_cookie(await entrar_como(ANA))
    conversa = (await cliente.post("/v1/conversas", headers=ana)).json()["id"]
    atacante = com_origem(ana, origem)
    inseguras = [(m, c) for m, c in rotas_protegidas(app) if m != "GET"]
    assert {("DELETE", "/v1/conta"), ("POST", "/v1/conversas")} <= set(inseguras)

    for metodo, caminho in [*inseguras, ("POST", "/v1/auth/sair")]:
        url = caminho.replace("{conversa_id}", conversa)
        r = await cliente.request(metodo, url, headers=atacante, json={"pergunta": "oi"})
        assert (r.status_code, r.json()) == (403, ORIGEM_NEGADA), (metodo, caminho)
        assert "set-cookie" not in r.headers

    assert await contar(sessao, Usuaria) == 1
    assert await contar(sessao, Conversa) == 1
    detalhe = await cliente.get(f"/v1/conversas/{conversa}", headers=ana)
    assert detalhe.json()["mensagens"] == []


async def test_origin_e_conferida_antes_da_sessao_e_do_corpo(cliente):
    invalido = {"Cookie": f"{COOKIE}=lixo"}
    r = await cliente.post("/v1/conversas/nao-e-uuid/mensagens", headers=invalido, json={})
    assert (r.status_code, r.json()) == (403, ORIGEM_NEGADA)


async def test_origin_repetida_e_recusada(cliente, entrar_como):
    ana = com_origem(em_cookie(await entrar_como(ANA)), None)
    for outra in (ORIGEM_DE_TESTE, "https://outro.example.org"):
        cabecalhos = [*ana.items(), ("Origin", ORIGEM_DE_TESTE), ("Origin", outra)]
        assert (await cliente.delete("/v1/conta", headers=cabecalhos)).status_code == 403


@pytest.mark.parametrize("origem", ORIGENS_ERRADAS[1:])
async def test_login_e_cadastro_com_origin_de_outro_site(cliente, sessao, origem):
    r = await cadastrar(cliente, Origin=origem)
    assert (r.status_code, r.json()) == (403, ORIGEM_NEGADA)
    assert await contar(sessao, Usuaria) == 0

    await cadastrar(cliente)
    r = await logar(cliente, Origin=origem)
    assert (r.status_code, r.json()) == (403, ORIGEM_NEGADA)
    assert "set-cookie" not in r.headers


@pytest.mark.parametrize("cabecalhos", [{}, {"Origin": ORIGEM_DE_TESTE}])
async def test_login_e_cadastro_sem_origin_ou_com_a_do_site(cliente, cabecalhos):
    assert (await cadastrar(cliente, **cabecalhos)).status_code == 201
    assert (await logar(cliente, **cabecalhos)).status_code == 200


async def test_authorization_tem_prioridade_e_dispensa_origin(cliente, entrar_como):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    cookie_da_bia = com_origem(em_cookie(bia), None)
    ambos = {**ana, **cookie_da_bia}
    assert (await cliente.get("/v1/conta", headers=ambos)).json()["email"] == ANA
    assert (await cliente.post("/v1/conversas", headers=ambos)).status_code == 201
    assert (await cliente.get("/v1/conversas", headers=bia)).json() == []
    assert (await cliente.delete("/v1/conta", headers=ambos)).status_code == 204
    assert (await cliente.get("/v1/conta", headers=bia)).json()["email"] == BIA


@pytest.mark.parametrize(
    "autorizacao", ["", "Bearer", "Bearer ", "Bearer lixo", "Basic YTpi", "lixo"]
)
async def test_authorization_invalida_da_401_mesmo_com_cookie_bom(
    cliente, entrar_como, autorizacao
):
    ana = em_cookie(await entrar_como(ANA))
    cabecalhos = {**ana, "Authorization": autorizacao}
    for metodo, url in [("GET", "/v1/conta"), ("DELETE", "/v1/conta")]:
        r = await cliente.request(metodo, url, headers=cabecalhos)
        assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)
    assert (await cliente.get("/v1/conta", headers=ana)).status_code == 200


async def test_authorization_repetida_e_recusada(cliente, entrar_como):
    bom = (await entrar_como(ANA))["Authorization"]
    for outra in (bom, "Bearer lixo", ""):
        for par in ((bom, outra), (outra, bom)):
            cabecalhos = [("Authorization", valor) for valor in par]
            r = await cliente.get("/v1/conta", headers=cabecalhos)
            assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)


async def test_cookie_de_sessao_repetido_e_recusado(cliente, entrar_como):
    bom = em_cookie(await entrar_como(ANA))["Cookie"]
    for outro in (bom, f"{COOKIE}=lixo", f"{COOKIE}="):
        for a, b in ((bom, outro), (outro, bom)):
            for cabecalhos in ([("Cookie", f"{a}; {b}")], [("Cookie", a), ("Cookie", b)]):
                r = await cliente.get("/v1/conta", headers=cabecalhos)
                assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)


async def test_outros_cookies_nao_atrapalham(cliente, entrar_como):
    bom = em_cookie(await entrar_como(ANA))["Cookie"]
    cookie = f"tema=claro; x{COOKIE}=lixo; ; solto;{bom}; {COOKIE.upper()}=lixo"
    r = await cliente.get("/v1/conta", headers={"Cookie": cookie})
    assert r.status_code == 200


async def test_nome_de_cookie_com_espaco_exotico_nao_e_a_sessao(cliente, entrar_como):
    """O navegador trata `\\xa0artemis_sessao` como outro nome; um strip comum os igualaria."""
    bom = em_cookie(await entrar_como(ANA))["Cookie"].encode()
    r = await cliente.get("/v1/conta", headers={b"Cookie": b"\xa0" + bom})
    assert r.status_code == 401


async def test_sair_e_excluir_conta_apagam_o_cookie(cliente, entrar_como):
    ana = em_cookie(await entrar_como(ANA))
    for metodo, url in [("POST", "/v1/auth/sair"), ("DELETE", "/v1/conta")]:
        r = await cliente.request(metodo, url, headers=ana)
        assert (r.status_code, r.content) == (204, b"")
        assert atributos_do_cookie(r) == APAGADO


async def test_sair_com_cookie_invalido_ou_repetido_apaga(cliente):
    for cookie in (f"{COOKIE}=lixo", f"{COOKIE}=a; {COOKIE}=b", f"{COOKIE}="):
        r = await cliente.post(
            "/v1/auth/sair", headers={"Cookie": cookie, "Origin": ORIGEM_DE_TESTE}
        )
        assert r.status_code == 204
        assert atributos_do_cookie(r) == APAGADO


async def test_sair_com_cookie_exige_origin_mesmo_com_authorization(cliente, entrar_como):
    """Sair age sobre o próprio cookie, então o cabeçalho não dispensa a origem."""
    ana = await entrar_como(ANA)
    cabecalhos = {**ana, **com_origem(em_cookie(ana), None)}
    r = await cliente.post("/v1/auth/sair", headers=cabecalhos)
    assert (r.status_code, r.json()) == (403, ORIGEM_NEGADA)
    assert "set-cookie" not in r.headers


async def test_conta_que_some_depois_do_token_responde_401(app, cliente):
    app.dependency_overrides[usuaria_atual] = uuid.uuid4
    r = await cliente.get("/v1/conta")
    assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)


@pytest.mark.parametrize("cabecalhos", [{}, {"Origin": "https://outro.example.org"}])
async def test_sair_sem_sessao_nao_mexe_no_cookie(cliente, cabecalhos):
    """Um formulário de outro site chega sem o cookie (SameSite); a resposta não pode apagá-lo."""
    r = await cliente.post("/v1/auth/sair", headers=cabecalhos)
    assert r.status_code == 204
    assert "set-cookie" not in r.headers


async def test_cookie_vencido_ou_adulterado(cliente, entrar_como):
    id_ = (await cliente.get("/v1/conta", headers=await entrar_como(ANA))).json()["id"]
    invalidos = [
        token(id_, exp=datetime.now(UTC) - timedelta(minutes=1)),
        token(id_, segredo="outro-segredo-falso-com-mais-de-32-bytes!!"),
        token(str(uuid.uuid4())),
        f'"{token(id_)}"',
        "",
        "lixo",
        "a.b.\xe9",
    ]
    for valor in invalidos:
        cabecalhos = {"Cookie": f"{COOKIE}={valor}".encode("latin-1"), "Origin": ORIGEM_DE_TESTE}
        for metodo, url in [("GET", "/v1/conta"), ("DELETE", "/v1/conta")]:
            r = await cliente.request(metodo, url, headers=cabecalhos)
            assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)
            assert r.headers["WWW-Authenticate"] == "Bearer"
            assert "set-cookie" not in r.headers


async def test_respostas_v1_nao_ficam_em_cache(app, cliente, entrar_como):
    @app.get("/v1/_teste/quebra")
    async def quebra() -> None:
        raise RuntimeError

    ana = await entrar_como(ANA)
    cookie = {"Cookie": em_cookie(ana)["Cookie"]}
    for metodo, url, cabecalhos, status in [
        ("GET", "/v1/consentimento", {}, 200),
        ("GET", "/v1/conta", ana, 200),
        ("POST", "/v1/auth/sair", {}, 204),
        ("GET", "/v1/conversas/", {}, 307),
        ("GET", "/v1/conta", {}, 401),
        ("DELETE", "/v1/conta", cookie, 403),
        ("GET", "/v1/nao-existe", {}, 404),
        ("GET", "/v1/auth/login", {}, 405),
        ("POST", "/v1/auth/login", {}, 422),
        ("GET", "/v1/_teste/quebra", {}, 500),
    ]:
        r = await cliente.request(metodo, url, headers=cabecalhos)
        assert r.status_code == status, (metodo, url)
        assert r.headers.get_list("cache-control") == ["no-store"], (metodo, url)
    assert "cache-control" not in (await cliente.get("/health")).headers


async def test_503_do_banco_nao_fica_em_cache(config, porta_fechada):
    url = f"postgresql+asyncpg://u:p@127.0.0.1:{porta_fechada}/d"
    app = criar_app(replace(config, database_url=url))
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        r = await logar(c)
    await app.state.motor.dispose()
    assert r.status_code == 503
    assert r.headers.get_list("cache-control") == ["no-store"]


async def test_logs_sem_cookie_nem_email(cliente, entrar_como, caplog):
    caplog.set_level(logging.DEBUG)
    ana = em_cookie(await entrar_como(ANA))
    await cliente.get("/v1/conta", headers=ana)
    await cliente.delete("/v1/conta", headers=com_origem(ana, None))
    await cliente.delete("/v1/conta", headers=ana)
    for segredo in (ANA, ana["Cookie"], ana["Cookie"].removeprefix(f"{COOKIE}=")):
        assert segredo not in caplog.text

import pytest

from artemis_backend.adapters.tabelas import Conversa, Usuaria
from tests.apoio.banco import contar
from tests.apoio.sessao import (
    COOKIE,
    ORIGEM_NEGADA,
    cadastrar,
    com_origem,
    em_cookie,
    logar,
    rotas_protegidas,
)
from tests.apoio.valores import ANA, ORIGEM_DE_TESTE

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

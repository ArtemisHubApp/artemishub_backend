import logging

import pytest

from artemis_backend.adapters.tabelas import Usuaria
from tests.apoio.banco import contar
from tests.apoio.sessao import em_cookie
from tests.apoio.valores import ANA, BIA, NOME_DE_TESTE, ORIGEM_DE_TESTE, SENHA_DE_TESTE

SEGREDO_NO_NOME = "Nome-Secreto-Zq"
ACEITOS = [
    ("  Ana   Souza ", "Ana Souza"),
    ("José da Conceição", "José da Conceição"),
    ("Zoë Ñandú", "Zoë Ñandú"),
    ("李小龙", "李小龙"),
    ("a" * 80, "a" * 80),
]
RECUSADOS = [
    "",
    "   ",
    "a" * 81,
    f"{SEGREDO_NO_NOME}\x00",
    f"{SEGREDO_NO_NOME}\n",
    7,
    None,
    ["Ana"],
]


def pedido(**mudancas) -> dict:
    corpo = {
        "nome": NOME_DE_TESTE,
        "email": ANA,
        "senha": SENHA_DE_TESTE,
        "consentimento": True,
    }
    return {k: v for k, v in {**corpo, **mudancas}.items() if v != "ausente"}


async def cadastrar(cliente, **mudancas):
    return await cliente.post("/v1/auth/cadastro", json=pedido(**mudancas))


@pytest.mark.parametrize(("enviado", "guardado"), ACEITOS)
async def test_cadastro_guarda_o_nome_normalizado(cliente, entrar_como, sessao, enviado, guardado):
    assert (await cadastrar(cliente, nome=enviado)).status_code == 201
    ana = await entrar_como(ANA)

    assert (await cliente.get("/v1/conta", headers=ana)).json()["nome"] == guardado


@pytest.mark.parametrize("nome", [*RECUSADOS, "ausente"])
async def test_cadastro_recusa_nome_invalido_sem_eco_e_sem_criar_conta(cliente, sessao, nome):
    r = await cadastrar(cliente, nome=nome)

    assert r.status_code == 422
    assert SEGREDO_NO_NOME not in r.text
    assert await contar(sessao, Usuaria) == 0


async def test_conta_devolve_id_nome_e_email(cliente, entrar_como):
    ana = await entrar_como(ANA)

    r = await cliente.get("/v1/conta", headers=ana)

    assert r.status_code == 200
    assert set(r.json()) == {"id", "nome", "email"}
    assert (r.json()["nome"], r.json()["email"]) == (NOME_DE_TESTE, ANA)


@pytest.mark.parametrize(("enviado", "guardado"), ACEITOS)
async def test_patch_troca_o_nome(cliente, entrar_como, enviado, guardado):
    ana = await entrar_como(ANA)
    antes = (await cliente.get("/v1/conta", headers=ana)).json()

    r = await cliente.patch("/v1/conta", json={"nome": enviado}, headers=ana)

    assert r.status_code == 200
    assert r.json() == {**antes, "nome": guardado}
    assert (await cliente.get("/v1/conta", headers=ana)).json() == r.json()


@pytest.mark.parametrize("nome", [*RECUSADOS, "ausente"])
async def test_patch_recusa_nome_invalido_sem_eco_e_nao_muda_nada(cliente, entrar_como, nome):
    ana = await entrar_como(ANA)
    corpo = {} if nome == "ausente" else {"nome": nome}

    r = await cliente.patch("/v1/conta", json=corpo, headers=ana)

    assert r.status_code == 422
    assert SEGREDO_NO_NOME not in r.text
    assert (await cliente.get("/v1/conta", headers=ana)).json()["nome"] == NOME_DE_TESTE


async def test_patch_so_muda_a_dona_do_token(cliente, entrar_como):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)

    r = await cliente.patch("/v1/conta", json={"nome": "Ana Nova"}, headers=ana)

    assert r.status_code == 200
    assert (await cliente.get("/v1/conta", headers=bia)).json()["nome"] == NOME_DE_TESTE
    assert (await cliente.get("/v1/conta", headers=ana)).json()["nome"] == "Ana Nova"


async def test_patch_ignora_id_e_email_no_corpo(cliente, entrar_como):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    id_da_bia = (await cliente.get("/v1/conta", headers=bia)).json()["id"]

    corpo = {"nome": "Ana Nova", "id": id_da_bia, "email": BIA}
    r = await cliente.patch("/v1/conta", json=corpo, headers=ana)

    assert r.status_code == 200
    assert (await cliente.get("/v1/conta", headers=bia)).json()["nome"] == NOME_DE_TESTE
    assert (await cliente.get("/v1/conta", headers=ana)).json()["email"] == ANA


@pytest.mark.parametrize("cabecalhos", [{}, {"Authorization": "Bearer lixo"}])
async def test_patch_sem_sessao_valida_responde_401(cliente, cabecalhos):
    r = await cliente.patch("/v1/conta", json={"nome": "Ana"}, headers=cabecalhos)

    assert r.status_code == 401


@pytest.mark.parametrize("origem", [None, "https://outro.example.org"])
async def test_patch_com_cookie_exige_origin(cliente, entrar_como, origem):
    ana = em_cookie(await entrar_como(ANA))
    cabecalhos = {"Cookie": ana["Cookie"], **({"Origin": origem} if origem else {})}

    r = await cliente.patch("/v1/conta", json={"nome": "Outra"}, headers=cabecalhos)

    assert r.status_code == 403
    assert (await cliente.get("/v1/conta", headers=ana)).json()["nome"] == NOME_DE_TESTE


async def test_patch_com_cookie_e_origin_certa(cliente, entrar_como):
    ana = em_cookie(await entrar_como(ANA))
    assert ana["Origin"] == ORIGEM_DE_TESTE

    r = await cliente.patch("/v1/conta", json={"nome": "Outra"}, headers=ana)

    assert r.status_code == 200
    assert r.json()["nome"] == "Outra"


async def test_excluir_a_conta_apaga_o_nome(cliente, entrar_como, sessao):
    ana = await entrar_como(ANA)

    assert (await cliente.delete("/v1/conta", headers=ana)).status_code == 204

    assert await contar(sessao, Usuaria, nome=NOME_DE_TESTE) == 0


async def test_nome_nao_vai_para_os_agentes_nem_para_o_log(cliente, entrar_como, agentes, caplog):
    nome = "Nome Fictício Rastreável"
    caplog.set_level(logging.DEBUG)
    assert (await cadastrar(cliente, nome=nome)).status_code == 201
    ana = await entrar_como(ANA)
    await cliente.patch("/v1/conta", json={"nome": nome + " Dois"}, headers=ana)
    id_ = (await cliente.post("/v1/conversas", headers=ana)).json()["id"]

    r = await cliente.post(f"/v1/conversas/{id_}/mensagens", json={"pergunta": "oi"}, headers=ana)

    assert r.status_code == 201
    assert "Rastreável" not in repr(agentes.chamadas)
    assert "Rastreável" not in caplog.text
    assert ANA not in caplog.text

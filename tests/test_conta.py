import asyncio
import time
import uuid

import pytest
from sqlalchemy import text

from artemis_backend.adapters.autenticacao import usuaria_atual
from artemis_backend.adapters.tabelas import Conversa, Mensagem, Usuaria
from artemis_backend.domain.usuaria import TokenInvalido
from tests.apoio.agentes import resposta_dos_agentes
from tests.apoio.banco import contar
from tests.apoio.sessao import em_cookie, rotas_protegidas
from tests.apoio.valores import ANA, BIA, NOME_DE_TESTE, SENHA_DE_TESTE

MENSAGENS_NO_VOLUME = 60_000
TEXTO_DO_CONSENTIMENTO = (
    "Guardamos suas conversas para você consultar depois. O texto das perguntas é enviado "
    "ao Google Gemini, para gerar a resposta, e ao Langfuse, para acompanhar a qualidade. "
    "No plano gratuito do Gemini, o Google pode usar esse texto para melhorar os produtos "
    "dele. Você pode apagar conversas e a conta quando quiser; os registros no Langfuse "
    "permanecem."
)


async def conversar(cliente, cabecalho, pergunta: str) -> str:
    id_ = (await cliente.post("/v1/conversas", headers=cabecalho)).json()["id"]
    r = await cliente.post(
        f"/v1/conversas/{id_}/mensagens", json={"pergunta": pergunta}, headers=cabecalho
    )
    assert r.status_code == 201
    return id_


async def test_sem_token_responde_401(cliente):
    for cabecalho in ({}, {"Authorization": "Bearer lixo"}):
        r = await cliente.delete("/v1/conta", headers=cabecalho)
        assert r.status_code == 401
        assert r.headers["WWW-Authenticate"] == "Bearer"


async def test_excluir_conta_apaga_tudo_dela_e_nada_das_outras(cliente, entrar_como, sessao):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    await conversar(cliente, ana, "pergunta da ana")
    await conversar(cliente, ana, "outra da ana")
    conversa_da_bia = await conversar(cliente, bia, "pergunta da bia")
    antes_da_bia = (await cliente.get(f"/v1/conversas/{conversa_da_bia}", headers=bia)).json()

    r = await cliente.delete("/v1/conta", headers=ana)

    assert r.status_code == 204
    assert r.content == b""
    assert await contar(sessao, Usuaria, email=ANA) == 0
    assert await contar(sessao, Usuaria) == 1
    assert await contar(sessao, Conversa) == 1
    assert await contar(sessao, Mensagem) == 2
    depois_da_bia = await cliente.get(f"/v1/conversas/{conversa_da_bia}", headers=bia)
    assert depois_da_bia.json() == antes_da_bia


def em_cabecalho(autorizacao: dict) -> dict:
    return autorizacao


@pytest.mark.parametrize("forma", [em_cabecalho, em_cookie])
async def test_token_de_conta_excluida_responde_401_em_toda_rota_protegida(
    app, cliente, entrar_como, forma
):
    ana = await entrar_como(ANA)
    assert (await cliente.delete("/v1/conta", headers=ana)).status_code == 204
    invalido = await cliente.get("/v1/conversas", headers={"Authorization": "Bearer lixo"})
    rotas = rotas_protegidas(app)
    assert {("DELETE", "/v1/conta"), ("GET", "/v1/conta"), ("GET", "/v1/conversas")} <= set(rotas)

    for metodo, caminho in rotas:
        url = caminho.replace("{conversa_id}", str(uuid.uuid4()))
        r = await cliente.request(metodo, url, headers=forma(ana), json={"pergunta": "oi"})
        assert r.status_code == 401, (metodo, caminho)
        assert r.json() == invalido.json()
        assert r.headers["WWW-Authenticate"] == "Bearer"


async def test_login_de_conta_excluida_responde_401(cliente, entrar_como):
    ana = await entrar_como(ANA)
    await cliente.delete("/v1/conta", headers=ana)
    r = await cliente.post("/v1/auth/login", json={"email": ANA, "senha": SENHA_DE_TESTE})
    assert r.status_code == 401


async def test_email_pode_ser_cadastrado_de_novo(cliente, entrar_como):
    ana = await entrar_como(ANA)
    await conversar(cliente, ana, "pergunta antiga")
    await cliente.delete("/v1/conta", headers=ana)

    r = await cliente.post(
        "/v1/auth/cadastro",
        json={
            "nome": NOME_DE_TESTE,
            "email": ANA,
            "senha": SENHA_DE_TESTE,
            "consentimento": True,
        },
    )

    assert r.status_code == 201
    nova = await entrar_como(ANA)
    assert (await cliente.get("/v1/conversas", headers=nova)).json()["itens"] == []
    assert (await cliente.get("/v1/conversas", headers=ana)).status_code == 401


async def test_servico_excluir_duas_vezes_recusa_a_segunda(app, cliente, entrar_como):
    ana = await entrar_como(ANA)
    id_ = await app.state.contas.usuaria_do_token(ana["Authorization"].removeprefix("Bearer "))

    await app.state.contas.excluir(id_)

    with pytest.raises(TokenInvalido):
        await app.state.contas.excluir(id_)


async def test_rota_com_conta_ja_excluida_responde_401_igual_ao_token_invalido(
    app, cliente, entrar_como
):
    ana = await entrar_como(ANA)
    id_ = await app.state.contas.usuaria_do_token(ana["Authorization"].removeprefix("Bearer "))
    await app.state.contas.excluir(id_)
    invalido = await cliente.get("/v1/conversas", headers={"Authorization": "Bearer lixo"})
    app.dependency_overrides[usuaria_atual] = lambda: id_
    try:
        r = await cliente.delete("/v1/conta")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 401
    assert r.json() == invalido.json()
    assert r.headers["WWW-Authenticate"] == "Bearer"


async def test_duas_exclusoes_ao_mesmo_tempo(cliente, entrar_como, sessao):
    ana = await entrar_como(ANA)
    invalido = await cliente.get("/v1/conversas", headers={"Authorization": "Bearer lixo"})

    respostas = await asyncio.gather(*(cliente.delete("/v1/conta", headers=ana) for _ in range(4)))

    assert sorted(r.status_code for r in respostas) == [204, 401, 401, 401]
    for r in respostas:
        if r.status_code == 401:
            assert r.json() == invalido.json()
    assert await contar(sessao, Usuaria) == 0


async def test_conta_excluida_durante_a_pergunta(cliente, entrar_como, sessao, agentes):
    ana = await entrar_como(ANA)
    id_ = (await cliente.post("/v1/conversas", headers=ana)).json()["id"]
    agentes.resposta = resposta_dos_agentes(resposta="tardia")
    agentes.bloquear()
    tarefa = asyncio.create_task(
        cliente.post(f"/v1/conversas/{id_}/mensagens", json={"pergunta": "lenta"}, headers=ana)
    )
    await asyncio.wait_for(agentes.chamado.wait(), 10)

    assert (await cliente.delete("/v1/conta", headers=ana)).status_code == 204
    agentes.liberar()

    assert (await tarefa).status_code == 404
    assert await contar(sessao, Usuaria) == 0
    assert await contar(sessao, Conversa) == 0
    assert await contar(sessao, Mensagem) == 0


async def test_consentimento_e_publico_e_cita_quem_recebe_o_texto(cliente):
    r = await cliente.get("/v1/consentimento")

    assert r.status_code == 200
    assert r.json() == {"texto": TEXTO_DO_CONSENTIMENTO}
    for termo in ("Gemini", "Langfuse", "permanecem"):
        assert termo in r.json()["texto"]


async def test_excluir_conta_com_muitas_mensagens_cabe_no_limite_do_banco(
    cliente, entrar_como, sessao
):
    """Sem índice em mensagens.pergunta_id, cada mensagem apagada varre a tabela inteira."""
    ana = await entrar_como(ANA)
    conversa = (await cliente.post("/v1/conversas", headers=ana)).json()["id"]
    await sessao.execute(
        text(
            "INSERT INTO mensagens (id, conversa_id, papel, texto) "
            "SELECT gen_random_uuid(), :conversa, 'usuaria', 'm' || n "
            "FROM generate_series(1, :total) AS n"
        ),
        {"conversa": uuid.UUID(conversa), "total": MENSAGENS_NO_VOLUME},
    )
    await sessao.commit()
    assert await contar(sessao, Mensagem) == MENSAGENS_NO_VOLUME

    inicio = time.monotonic()
    r = await cliente.delete("/v1/conta", headers=ana)
    duracao = time.monotonic() - inicio

    assert r.status_code == 204
    assert duracao < 5, f"exclusão levou {duracao:.1f}s"
    assert await contar(sessao, Mensagem) == 0

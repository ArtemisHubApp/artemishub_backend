import uuid

import pytest
from sqlalchemy import func, select

from artemis_backend.adapters.tabelas import Conversa
from tests.apoio.conversas import CAMPOS_DA_CONVERSA, gravar, mensagem, nova_conversa
from tests.apoio.valores import ANA, BIA


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("GET", "/v1/conversas"),
        ("POST", "/v1/conversas"),
        ("GET", f"/v1/conversas/{uuid.uuid4()}"),
        ("DELETE", f"/v1/conversas/{uuid.uuid4()}"),
    ],
)
async def test_sem_token_responde_401(cliente, metodo, caminho):
    for cabecalho in ({}, {"Authorization": "Bearer lixo"}):
        r = await cliente.request(metodo, caminho, headers=cabecalho)
        assert r.status_code == 401


async def test_cria_conversa_vazia(cliente, entrar_como):
    cabecalho = await entrar_como(ANA)
    r = await cliente.post("/v1/conversas", headers=cabecalho)
    assert r.status_code == 201
    corpo = r.json()
    assert set(corpo) == CAMPOS_DA_CONVERSA
    assert corpo["titulo"] is None
    assert uuid.UUID(corpo["id"])

    detalhe = await cliente.get(f"/v1/conversas/{corpo['id']}", headers=cabecalho)
    assert detalhe.status_code == 200
    assert detalhe.json()["mensagens"] == []


async def test_conversa_de_outra_usuaria_responde_404(cliente, entrar_como, sessao):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    id_ = await nova_conversa(cliente, ana)
    await gravar(sessao, mensagem(id_, "usuaria", "segredo da ana"))
    inexistente = str(uuid.uuid4())

    for metodo in ("GET", "DELETE"):
        alheia = await cliente.request(metodo, f"/v1/conversas/{id_}", headers=bia)
        nenhuma = await cliente.request(metodo, f"/v1/conversas/{inexistente}", headers=bia)
        assert alheia.status_code == nenhuma.status_code == 404
        assert alheia.json() == nenhuma.json()
        assert "segredo" not in alheia.text

    da_dona = await cliente.get(f"/v1/conversas/{id_}", headers=ana)
    assert da_dona.status_code == 200
    assert [m["texto"] for m in da_dona.json()["mensagens"]] == ["segredo da ana"]


async def test_id_malformado_responde_422(cliente, entrar_como):
    cabecalho = await entrar_como(ANA)
    for metodo in ("GET", "DELETE"):
        r = await cliente.request(metodo, "/v1/conversas/nao-e-uuid", headers=cabecalho)
        assert r.status_code == 422


async def test_conta_apagada_antes_de_criar_conversa_responde_401(app, cliente, sessao, caplog):
    from artemis_backend.adapters.autenticacao import usuaria_atual

    fantasma = uuid.uuid4()
    app.dependency_overrides[usuaria_atual] = lambda: fantasma
    try:
        r = await cliente.post("/v1/conversas")
    finally:
        app.dependency_overrides.clear()
    invalido = await cliente.get("/v1/conversas", headers={"Authorization": "Bearer lixo"})

    assert r.status_code == 401
    assert r.json() == invalido.json()
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert await sessao.scalar(select(func.count()).select_from(Conversa)) == 0
    assert "@" not in caplog.text


async def test_outra_violacao_de_integridade_continua_subindo(app, entrar_como):
    from sqlalchemy.exc import IntegrityError

    await entrar_como(ANA)
    usuaria_id = await app.state.contas._repositorio.por_email(ANA)
    repositorio = app.state.conversas._repositorio
    conversa_id = uuid.uuid4()
    await repositorio.criar(usuaria_id.id, conversa_id)
    with pytest.raises(IntegrityError):
        await repositorio.criar(usuaria_id.id, conversa_id)

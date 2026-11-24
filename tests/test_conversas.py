import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

from artemis_backend.adapters.banco import criar_fabrica_de_sessoes
from artemis_backend.adapters.tabelas import Conversa, Mensagem

ANA = "ana@example.com"
BIA = "bia@example.com"
INICIO = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
CAMPOS_DA_CONVERSA = {"id", "titulo", "criada_em", "atualizada_em"}


@pytest_asyncio.fixture
async def sessao(app):
    async with criar_fabrica_de_sessoes(app.state.motor)() as s:
        yield s


async def nova_conversa(cliente, cabecalho) -> str:
    r = await cliente.post("/v1/conversas", headers=cabecalho)
    assert r.status_code == 201
    return r.json()["id"]


def mensagem(conversa_id: str, papel: str, texto: str, segundos: int = 0, **extra) -> Mensagem:
    return Mensagem(
        id=uuid.uuid4(),
        conversa_id=uuid.UUID(conversa_id),
        papel=papel,
        texto=texto,
        criada_em=INICIO + timedelta(seconds=segundos),
        **extra,
    )


async def gravar(sessao, *mensagens: Mensagem) -> None:
    sessao.add_all(mensagens)
    await sessao.commit()


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


async def test_lista_vazia(cliente, entrar_como):
    r = await cliente.get("/v1/conversas", headers=await entrar_como(ANA))
    assert r.status_code == 200
    assert r.json() == []


async def test_lista_mais_recente_primeiro(cliente, entrar_como, sessao):
    cabecalho = await entrar_como(ANA)
    ids = [await nova_conversa(cliente, cabecalho) for _ in range(3)]
    # A do meio foi atualizada por último.
    for posicao, id_ in zip([2, 0, 1], ids, strict=True):
        await sessao.execute(
            update(Conversa)
            .where(Conversa.id == uuid.UUID(id_))
            .values(atualizada_em=INICIO + timedelta(hours=posicao))
        )
    await sessao.commit()

    r = await cliente.get("/v1/conversas", headers=cabecalho)
    assert [c["id"] for c in r.json()] == [ids[0], ids[2], ids[1]]


async def test_lista_com_empate_tem_ordem_fixa(cliente, entrar_como, sessao):
    cabecalho = await entrar_como(ANA)
    ids = [await nova_conversa(cliente, cabecalho) for _ in range(4)]
    await sessao.execute(update(Conversa).values(atualizada_em=INICIO, criada_em=INICIO))
    await sessao.commit()

    ordens = {
        tuple(c["id"] for c in (await cliente.get("/v1/conversas", headers=cabecalho)).json())
        for _ in range(3)
    }
    assert ordens == {tuple(sorted(ids, reverse=True))}


async def test_lista_so_tem_as_conversas_da_usuaria(cliente, entrar_como):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    da_ana = await nova_conversa(cliente, ana)
    da_bia = await nova_conversa(cliente, bia)

    ids_da_ana = [c["id"] for c in (await cliente.get("/v1/conversas", headers=ana)).json()]
    ids_da_bia = [c["id"] for c in (await cliente.get("/v1/conversas", headers=bia)).json()]
    assert ids_da_ana == [da_ana]
    assert ids_da_bia == [da_bia]


async def test_detalhe_traz_as_mensagens_na_ordem_com_a_pergunta_antes_da_resposta(
    cliente, entrar_como, sessao
):
    cabecalho = await entrar_como(ANA)
    id_ = await nova_conversa(cliente, cabecalho)
    p1 = mensagem(id_, "usuaria", "p1", segundos=0)
    r1 = mensagem(id_, "artemis", "r1", segundos=0, pergunta_id=p1.id, aprovada=True)
    p2 = mensagem(id_, "usuaria", "p2", segundos=60)
    r2 = mensagem(id_, "artemis", "r2", segundos=60, pergunta_id=p2.id, aprovada=True)
    # Gravadas fora de ordem, com empate de data entre pergunta e resposta.
    await gravar(sessao, p1)
    await gravar(sessao, p2)
    await gravar(sessao, r2, r1)

    for _ in range(3):
        r = await cliente.get(f"/v1/conversas/{id_}", headers=cabecalho)
        assert [m["texto"] for m in r.json()["mensagens"]] == ["p1", "r1", "p2", "r2"]


async def test_detalhe_mostra_so_os_campos_publicos(cliente, entrar_como, sessao):
    cabecalho = await entrar_como(ANA)
    id_ = await nova_conversa(cliente, cabecalho)
    await sessao.execute(
        update(Conversa)
        .where(Conversa.id == uuid.UUID(id_))
        .values(lembranca={"ocupacao": "segredo-da-lembranca"}, respondendo_desde=INICIO)
    )
    p = mensagem(id_, "usuaria", "pergunta")
    await gravar(
        sessao,
        p,
        mensagem(
            id_,
            "artemis",
            "resposta",
            segundos=1,
            pergunta_id=p.id,
            aprovada=True,
            trace_id="trace-secreto",
        ),
    )

    r = await cliente.get(f"/v1/conversas/{id_}", headers=cabecalho)
    lista = await cliente.get("/v1/conversas", headers=cabecalho)
    corpo = r.json()
    assert set(corpo) == CAMPOS_DA_CONVERSA | {"mensagens"}
    assert set(corpo["mensagens"][1]) == {
        "id",
        "papel",
        "texto",
        "criada_em",
        "aprovada",
        "bloqueada",
        "pergunta_id",
    }
    assert corpo["mensagens"][1]["aprovada"] is True
    assert corpo["mensagens"][1]["pergunta_id"] == corpo["mensagens"][0]["id"]
    for texto in (r.text, lista.text):
        for proibido in (
            "usuaria_id",
            "lembranca",
            "segredo-da-lembranca",
            "respondendo_desde",
            "trace",
            ANA,
        ):
            assert proibido not in texto


async def test_datas_saem_em_utc(cliente, entrar_como, sessao):
    cabecalho = await entrar_como(ANA)
    id_ = await nova_conversa(cliente, cabecalho)
    await gravar(sessao, mensagem(id_, "usuaria", "oi"))

    corpo = (await cliente.get(f"/v1/conversas/{id_}", headers=cabecalho)).json()
    datas = [corpo["criada_em"], corpo["atualizada_em"], corpo["mensagens"][0]["criada_em"]]
    for data in datas:
        analisada = datetime.fromisoformat(data)
        assert analisada.utcoffset() == timedelta(0)
        assert data.endswith(("Z", "+00:00"))
    assert datetime.fromisoformat(datas[2]) == INICIO


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


async def test_apagar_conversa_apaga_mensagens(cliente, entrar_como, sessao):
    cabecalho = await entrar_como(ANA)
    id_ = await nova_conversa(cliente, cabecalho)
    outra = await nova_conversa(cliente, cabecalho)
    p = mensagem(id_, "usuaria", "p")
    await gravar(sessao, p)
    await gravar(sessao, mensagem(id_, "artemis", "r", segundos=1, pergunta_id=p.id))
    await gravar(sessao, mensagem(outra, "usuaria", "fica"))

    r = await cliente.delete(f"/v1/conversas/{id_}", headers=cabecalho)
    assert r.status_code == 204
    assert r.content == b""
    segunda = await cliente.delete(f"/v1/conversas/{id_}", headers=cabecalho)
    assert segunda.status_code == 404
    assert (await cliente.get(f"/v1/conversas/{id_}", headers=cabecalho)).status_code == 404

    sessao.expire_all()
    restantes = await sessao.scalars(select(Mensagem.texto))
    assert list(restantes) == ["fica"]
    assert await sessao.scalar(select(func.count()).select_from(Conversa)) == 1


async def test_apagar_duas_vezes_ao_mesmo_tempo_nao_da_500(cliente, entrar_como):
    cabecalho = await entrar_como(ANA)
    for _ in range(5):
        id_ = await nova_conversa(cliente, cabecalho)
        respostas = await asyncio.gather(
            *(cliente.delete(f"/v1/conversas/{id_}", headers=cabecalho) for _ in range(4))
        )
        assert sorted(r.status_code for r in respostas) == [204, 404, 404, 404]


async def test_conta_apagada_antes_de_criar_conversa_responde_401(app, cliente, sessao, caplog):
    from artemis_backend.adapters.rotas_auth import usuaria_atual

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

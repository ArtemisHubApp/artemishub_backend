import uuid
from datetime import datetime, timedelta

from sqlalchemy import update

from artemis_backend.adapters.tabelas import Conversa
from tests.apoio.conversas import CAMPOS_DA_CONVERSA, INICIO, gravar, mensagem, nova_conversa
from tests.apoio.valores import ANA


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

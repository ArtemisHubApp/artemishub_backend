import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func

from artemis_backend.adapters.banco import criar_fabrica_de_sessoes
from artemis_backend.adapters.repositorio_perguntas import RepositorioPerguntasSql
from artemis_backend.domain.conversa import NovaResposta
from tests.apoio.agentes import resposta_dos_agentes
from tests.apoio.banco import linha, mudar, total_de_mensagens
from tests.apoio.conversas import LEMBRANCA


async def test_trava_recente_responde_409(perguntar, sessao, conversa, agentes):
    await mudar(sessao, conversa, respondendo_desde=func.now() - timedelta(seconds=50))
    antes = (await linha(sessao, conversa)).respondendo_desde
    r = await perguntar()
    assert r.status_code == 409 and agentes.chamadas == []
    assert (await linha(sessao, conversa)).respondendo_desde == antes
    assert await total_de_mensagens(sessao) == 0


async def test_trava_velha_expira(perguntar, sessao, conversa):
    await mudar(sessao, conversa, respondendo_desde=func.now() - timedelta(seconds=61))
    assert (await perguntar()).status_code == 201
    assert (await linha(sessao, conversa)).respondendo_desde is None


async def test_duas_perguntas_disputam_a_trava_velha(perguntar, sessao, conversa, agentes):
    await mudar(sessao, conversa, respondendo_desde=func.now() - timedelta(seconds=61))
    agentes.bloquear()
    tarefas = [asyncio.create_task(perguntar(f"p{i}")) for i in range(2)]
    prontas, presas = await asyncio.wait(tarefas, timeout=10, return_when=asyncio.FIRST_COMPLETED)
    assert [t.result().status_code for t in prontas] == [409]
    agentes.liberar()
    assert (await presas.pop()).status_code == 201


async def test_trava_tomada_por_outra_descarta_a_resposta_tardia(
    perguntar, mensagens, sessao, conversa, agentes
):
    agentes.resposta = resposta_dos_agentes(resposta="tardia", lembranca=LEMBRANCA)
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar("lenta"))
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    nova = datetime.now(UTC)
    await mudar(sessao, conversa, respondendo_desde=nova)
    agentes.liberar()

    assert (await tarefa).status_code == 409
    assert [m["texto"] for m in await mensagens()] == ["lenta"]
    depois = await linha(sessao, conversa)
    assert depois.respondendo_desde == nova and depois.lembranca is None


async def test_trava_expirada_tomada_e_ja_concluida_descarta_a_tardia(
    perguntar, mensagens, sessao, conversa, agentes
):
    agentes.bloquear()
    lenta = asyncio.create_task(perguntar("lenta"))
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    await mudar(sessao, conversa, respondendo_desde=func.now() - timedelta(seconds=61))
    rapida = asyncio.create_task(perguntar("rápida"))
    async with asyncio.timeout(10):
        while len(agentes.chamadas) < 2:
            await asyncio.sleep(0.01)
    agentes.liberar()
    assert sorted([(await lenta).status_code, (await rapida).status_code]) == [201, 409]
    assert (await rapida).status_code == 201
    assert [m["texto"] for m in await mensagens()] == ["lenta", "rápida", agentes.resposta.resposta]


async def test_trava_vencida_e_nao_tomada_ainda_grava_a_resposta(app, sessao, conversa):
    desde = datetime.now(UTC) - timedelta(seconds=61)
    await mudar(sessao, conversa, respondendo_desde=desde)
    dona = (await linha(sessao, conversa)).usuaria_id
    repositorio = RepositorioPerguntasSql(criar_fabrica_de_sessoes(app.state.motor))
    resposta = NovaResposta(uuid.uuid4(), "no limite", False, False, None, None)
    gravada = await repositorio.concluir_pergunta(dona, uuid.UUID(conversa), desde, resposta, None)
    assert gravada.texto == "no limite"
    assert await total_de_mensagens(sessao) == 1
    assert (await linha(sessao, conversa)).respondendo_desde is None

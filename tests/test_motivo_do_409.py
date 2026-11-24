import asyncio
from datetime import UTC, datetime

from sqlalchemy import func

from tests.apoio.banco import mudar, total_de_mensagens

OCUPADA = {"detail": "Já há uma pergunta em andamento nesta conversa", "codigo": "ocupada"}
EXPIRADA = {
    "detail": "A resposta demorou demais e foi descartada; a pergunta está no histórico",
    "codigo": "expirada",
}


async def test_409_ocupada_nao_grava_a_pergunta(perguntar, sessao, conversa, agentes):
    await mudar(sessao, conversa, respondendo_desde=func.now())
    r = await perguntar()
    assert (r.status_code, r.json()) == (409, OCUPADA)
    assert await total_de_mensagens(sessao) == 0 and agentes.chamadas == []


async def test_409_expirada_deixa_a_pergunta_no_historico(
    perguntar, mensagens, sessao, conversa, agentes
):
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar("lenta"))
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    await mudar(sessao, conversa, respondendo_desde=datetime.now(UTC))
    agentes.liberar()

    r = await tarefa
    assert (r.status_code, r.json()) == (409, EXPIRADA)
    assert [m["texto"] for m in await mensagens()] == ["lenta"]

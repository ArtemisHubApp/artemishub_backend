import asyncio

from sqlalchemy import delete, func, select

from artemis_backend.adapters.tabelas import Usuaria
from tests.apoio.banco import linha, total_de_mensagens


async def test_conversa_apagada_durante_a_resposta(
    cliente, ana, perguntar, conversa, sessao, agentes
):
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar())
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    r = await cliente.delete(f"/v1/conversas/{conversa}", headers=ana)
    assert r.status_code == 204
    agentes.liberar()
    assert (await tarefa).status_code == 404
    assert await total_de_mensagens(sessao) == 0
    assert await linha(sessao, conversa) is None


async def test_conta_apagada_durante_a_resposta(perguntar, sessao, conversa, agentes):
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar())
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    await sessao.execute(delete(Usuaria))
    await sessao.commit()
    agentes.liberar()
    assert (await tarefa).status_code == 404
    assert await total_de_mensagens(sessao) == 0
    assert await linha(sessao, conversa) is None
    assert await sessao.scalar(select(func.count()).select_from(Usuaria)) == 0

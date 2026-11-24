import asyncio

from sqlalchemy import text

from tests.apoio.banco import total_de_mensagens


async def test_duas_perguntas_ao_mesmo_tempo(perguntar, agentes, sessao):
    agentes.bloquear()
    tarefas = [asyncio.create_task(perguntar(f"p{i}")) for i in range(2)]
    # A perdedora termina enquanto a vencedora ainda está presa nos agentes.
    prontas, presas = await asyncio.wait(tarefas, timeout=10, return_when=asyncio.FIRST_COMPLETED)
    assert len(prontas) == len(presas) == 1
    assert prontas.pop().result().status_code == 409
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    assert await total_de_mensagens(sessao) == 1
    agentes.liberar()
    assert (await presas.pop()).status_code == 201
    assert len(agentes.chamadas) == 1 and await total_de_mensagens(sessao) == 2


async def test_dez_perguntas_ao_mesmo_tempo_so_uma_passa(perguntar, agentes):
    agentes.bloquear()
    tarefas = [asyncio.create_task(perguntar(f"p{i}")) for i in range(10)]
    while sum(t.done() for t in tarefas) < 9:
        await asyncio.wait(
            [t for t in tarefas if not t.done()], timeout=10, return_when="FIRST_COMPLETED"
        )
    agentes.liberar()
    status = sorted(r.status_code for r in await asyncio.gather(*tarefas))
    assert status == [201] + [409] * 9 and len(agentes.chamadas) == 1


async def test_conversas_diferentes_nao_se_travam(cliente, ana, perguntar, agentes):
    outra = (await cliente.post("/v1/conversas", headers=ana)).json()["id"]
    agentes.bloquear()
    tarefas = [
        asyncio.create_task(perguntar()),
        asyncio.create_task(perguntar(id_=outra)),
    ]
    async with asyncio.timeout(10):
        while len(agentes.chamadas) < 2:
            await asyncio.sleep(0.01)
    agentes.liberar()
    assert [r.status_code for r in await asyncio.gather(*tarefas)] == [201, 201]


async def test_banco_fica_livre_enquanto_os_agentes_respondem(app, perguntar, sessao, agentes):
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar())
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    assert app.state.motor.pool.checkedout() == 0
    # A pergunta já está confirmada no banco e ninguém segura transação aberta.
    assert await total_de_mensagens(sessao) == 1
    abertas = await sessao.scalar(
        text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
            "AND state LIKE 'idle in transaction%' AND pid <> pg_backend_pid()"
        )
    )
    assert abertas == 0
    agentes.liberar()
    assert (await tarefa).status_code == 201

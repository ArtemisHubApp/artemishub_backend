import asyncio

import pytest

from artemis_backend.adapters.tabelas import Conversa, Mensagem, Usuaria
from tests.apoio.banco import contar
from tests.apoio.conversas import nova_conversa
from tests.apoio.sessao import ORIGEM_NEGADA, com_origem, em_cookie
from tests.apoio.valores import ANA, BIA

ROTA = "/v1/conversas"


async def test_apagar_todas_so_as_da_usuaria(cliente, entrar_como, sessao):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    for _ in range(2):
        id_ = await nova_conversa(cliente, ana)
        await cliente.post(f"{ROTA}/{id_}/mensagens", json={"pergunta": "da ana"}, headers=ana)
    da_bia = await nova_conversa(cliente, bia)
    await cliente.post(f"{ROTA}/{da_bia}/mensagens", json={"pergunta": "da bia"}, headers=bia)
    antes = (await cliente.get(f"{ROTA}/{da_bia}", headers=bia)).json()

    for _ in range(2):  # repetir, já sem nenhuma, também é 204
        r = await cliente.delete(ROTA, headers=ana)
        assert (r.status_code, r.content) == (204, b"")

    assert await contar(sessao, Conversa) == 1
    assert await contar(sessao, Mensagem) == 2
    assert await contar(sessao, Usuaria) == 2
    assert (await cliente.get(f"{ROTA}/{da_bia}", headers=bia)).json() == antes


@pytest.mark.parametrize("origem", [None, "null", "https://outro.example.org"])
async def test_apagar_todas_com_cookie_exige_origin(cliente, entrar_como, sessao, origem):
    ana = em_cookie(await entrar_como(ANA))
    await nova_conversa(cliente, ana)

    negada = await cliente.delete(ROTA, headers=com_origem(ana, origem))
    assert (negada.status_code, negada.json()) == (403, ORIGEM_NEGADA)
    assert await contar(sessao, Conversa) == 1

    assert (await cliente.delete(ROTA, headers=ana)).status_code == 204
    assert await contar(sessao, Conversa) == 0


async def test_apagar_todas_sem_sessao(cliente):
    assert (await cliente.delete(ROTA)).status_code == 401


async def test_apagar_todas_durante_uma_pergunta(cliente, ana, perguntar, sessao, agentes):
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar())
    await asyncio.wait_for(agentes.chamado.wait(), 10)

    assert (await cliente.delete(ROTA, headers=ana)).status_code == 204
    agentes.liberar()

    assert (await tarefa).status_code == 404
    assert await contar(sessao, Conversa) == 0
    assert await contar(sessao, Mensagem) == 0


async def test_apagar_todas_ao_mesmo_tempo_nao_da_500(cliente, ana, sessao):
    for _ in range(5):
        for _ in range(10):
            await nova_conversa(cliente, ana)
        respostas = await asyncio.gather(*(cliente.delete(ROTA, headers=ana) for _ in range(4)))
        assert [r.status_code for r in respostas] == [204] * 4
    assert await contar(sessao, Conversa) == 0

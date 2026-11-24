import uuid
from datetime import timedelta

from sqlalchemy import update

from artemis_backend.adapters.tabelas import Conversa
from tests.apoio.conversas import INICIO, nova_conversa
from tests.apoio.valores import ANA, BIA


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

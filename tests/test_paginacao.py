import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from artemis_backend.adapters.tabelas import Conversa, Usuaria
from tests.apoio.conversas import CAMPOS_DA_CONVERSA, INICIO, nova_conversa
from tests.apoio.valores import ANA, BIA

ROTA = "/v1/conversas"


@pytest.fixture
def semear(sessao):
    """Cria conversas com as datas dadas (atualizada_em, criada_em) e devolve a ordem da lista."""

    async def criar(email: str, datas: list) -> list[str]:
        dona = await sessao.scalar(select(Usuaria.id).where(Usuaria.email == email))
        novas = [
            Conversa(id=uuid.uuid4(), usuaria_id=dona, atualizada_em=a, criada_em=c)
            for a, c in datas
        ]
        sessao.add_all(novas)
        await sessao.commit()
        ordem = sorted(novas, key=lambda c: (c.atualizada_em, c.criada_em, c.id), reverse=True)
        return [str(c.id) for c in ordem]

    return criar


@pytest.fixture
def paginas(cliente):
    """Percorre a lista até `proximo` nulo e devolve os ids de cada página."""

    async def ler(cabecalho, **parametros) -> list[list[str]]:
        lidas = []
        while True:
            r = await cliente.get(ROTA, headers=cabecalho, params=parametros)
            assert r.status_code == 200
            corpo = r.json()
            assert isinstance(corpo, dict) and set(corpo) == {"itens", "proximo"}
            lidas.append([c["id"] for c in corpo["itens"]])
            if corpo["proximo"] is None:
                return lidas
            assert len(lidas) < 200
            parametros["cursor"] = corpo["proximo"]

    return ler


async def test_paginas_sem_repetir_nem_pular(ana, semear, paginas):
    # Empates em atualizada_em e, dentro deles, em criada_em: só o id desempata.
    datas = [
        (INICIO + timedelta(hours=n // 40), INICIO + timedelta(minutes=n // 20)) for n in range(120)
    ]
    esperadas = await semear(ANA, datas)
    lidas = await paginas(ana)
    assert [len(p) for p in lidas] == [50, 50, 20]
    assert sum(lidas, []) == esperadas
    assert sum(await paginas(ana, limite=7), []) == esperadas


async def test_pagina_cheia_exata_nao_tem_proxima(ana, semear, paginas):
    await semear(ANA, [(INICIO, INICIO)] * 100)
    assert [len(p) for p in await paginas(ana, limite=100)] == [100]


async def test_microssegundos_vizinhos_nao_se_perdem(ana, semear, paginas):
    um = timedelta(microseconds=1)
    datas = [(INICIO + n * um, INICIO) for n in range(5)]
    datas += [(INICIO, INICIO + n * um) for n in range(1, 5)]
    esperadas = await semear(ANA, datas)
    assert sum(await paginas(ana, limite=1), []) == esperadas


async def test_item_so_tem_os_campos_publicos(cliente, ana, conversa):
    [item] = (await cliente.get(ROTA, headers=ana)).json()["itens"]
    assert item["id"] == conversa
    assert set(item) == CAMPOS_DA_CONVERSA


async def test_cursor_de_outra_usuaria_nao_vaza(cliente, entrar_como, semear):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    await semear(ANA, [(INICIO + timedelta(hours=n), INICIO) for n in range(4)])
    da_bia = await semear(BIA, [(INICIO + timedelta(minutes=30), INICIO)])
    da_ana = await cliente.get(ROTA, headers=ana, params={"limite": 2})

    r = await cliente.get(ROTA, headers=bia, params={"cursor": da_ana.json()["proximo"]})

    assert [c["id"] for c in r.json()["itens"]] == da_bia


async def test_cursor_de_conversa_apagada_continua_valendo(cliente, ana, semear):
    ids = await semear(ANA, [(INICIO + timedelta(hours=n), INICIO) for n in range(3)])
    cursor = (await cliente.get(ROTA, headers=ana, params={"limite": 1})).json()["proximo"]
    await cliente.delete(f"{ROTA}/{ids[0]}", headers=ana)
    r = await cliente.get(ROTA, headers=ana, params={"cursor": cursor})
    assert [c["id"] for c in r.json()["itens"]] == ids[1:]


async def test_conversa_nova_entre_paginas_nao_repete_as_antigas(cliente, ana, semear):
    ids = await semear(ANA, [(INICIO + timedelta(hours=n), INICIO) for n in range(3)])
    cursor = (await cliente.get(ROTA, headers=ana, params={"limite": 1})).json()["proximo"]
    nova = await nova_conversa(cliente, ana)
    r = await cliente.get(ROTA, headers=ana, params={"cursor": cursor})
    assert [c["id"] for c in r.json()["itens"] if c["id"] != nova] == ids[1:]

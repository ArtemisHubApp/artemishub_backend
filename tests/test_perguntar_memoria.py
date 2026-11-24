import pytest

from artemis_backend.application.perguntar import AgentesIndisponiveis
from artemis_backend.domain.conversa import Troca
from tests.apoio.agentes import resposta_dos_agentes
from tests.apoio.banco import linha, mudar
from tests.apoio.conversas import LEMBRANCA

OUTRA = {**LEMBRANCA, "uf": "RJ"}


async def test_manda_historico_e_lembranca_da_conversa(perguntar, sessao, conversa, agentes):
    await mudar(sessao, conversa, lembranca=LEMBRANCA)
    for i in range(1, 5):
        agentes.resposta = resposta_dos_agentes(resposta=f"r{i}")
        assert (await perguntar(f"p{i}")).status_code == 201
    await perguntar("  p5 ")

    assert agentes.chamadas[0] == ("p1", conversa, [], LEMBRANCA)
    assert agentes.chamadas[-1] == (
        "p5",
        conversa,
        [Troca("p2", "r2"), Troca("p3", "r3"), Troca("p4", "r4")],
        LEMBRANCA,
    )


async def test_historico_so_tem_a_mesma_conversa(cliente, ana, perguntar, agentes):
    await perguntar("da primeira")
    outra = (await cliente.post("/v1/conversas", headers=ana)).json()["id"]
    await perguntar("da segunda", id_=outra)
    assert agentes.chamadas[-1] == ("da segunda", outra, [], None)


async def test_nao_aprovada_e_indisponivel_ficam_fora_do_historico(perguntar, agentes):
    agentes.resposta = resposta_dos_agentes(aprovada=False)
    await perguntar("abstenção")
    agentes.resposta = resposta_dos_agentes(bloqueada=True)
    await perguntar("bloqueada")
    agentes.resposta = resposta_dos_agentes(aprovada=True, fora_de_escopo=True)
    fora = await perguntar("fora de escopo")
    agentes.erro = AgentesIndisponiveis()
    await perguntar("erro")
    agentes.erro = None
    await perguntar("última")
    assert agentes.chamadas[-1][2] == []
    assert fora.json()["resposta"]["aprovada"] is False


async def test_lembranca_nova_e_guardada(perguntar, sessao, conversa, agentes):
    await mudar(sessao, conversa, lembranca=LEMBRANCA)
    agentes.resposta = resposta_dos_agentes(lembranca=OUTRA)
    await perguntar()
    assert (await linha(sessao, conversa)).lembranca == OUTRA
    await perguntar()
    assert agentes.chamadas[-1][3] == OUTRA


@pytest.mark.parametrize(
    "extra",
    [
        {"bloqueada": True, "lembranca": OUTRA},
        {"fora_de_escopo": True, "lembranca": OUTRA},
        {"lembranca": None},
    ],
)
async def test_bloqueada_nao_altera_a_lembranca(perguntar, sessao, conversa, agentes, extra):
    await mudar(sessao, conversa, lembranca=LEMBRANCA)
    agentes.resposta = resposta_dos_agentes(**extra)
    assert (await perguntar()).status_code == 201
    assert (await linha(sessao, conversa)).lembranca == LEMBRANCA


async def test_bloqueada_nunca_fica_aprovada(perguntar, mensagens, agentes):
    agentes.resposta = resposta_dos_agentes(aprovada=True, bloqueada=True)
    r = await perguntar()
    assert (r.json()["resposta"]["aprovada"], r.json()["resposta"]["bloqueada"]) == (False, True)
    assert (await mensagens())[-1] == r.json()["resposta"]

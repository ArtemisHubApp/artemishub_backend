import re
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from artemis_backend.adapters.agentes_http import AgentesHttp
from artemis_backend.application.portas import AgentesIndisponiveis
from artemis_backend.domain.conversa import Troca
from tests.apoio.contrato import validador
from tests.apoio.conversas import LEMBRANCA
from tests.apoio.simulador import AUTORIZADA, TOKEN, pedido, simulador_no_ar

ROTA = "/v1/responder"


@pytest.fixture
def esperas() -> list[float]:
    return []


@pytest.fixture
def url(esperas):
    with simulador_no_ar(esperas.append) as base:
        yield base


def perguntar(url: str, pergunta: str) -> httpx.Response:
    return httpx.post(url + ROTA, json=pedido(pergunta), headers=AUTORIZADA, trust_env=False)


@pytest.mark.parametrize(
    "pergunta", ["oi", "é #bloqueada?", "#escopo", "#lento", "\U0001f319" * 1000]
)
def test_simulador_segue_o_contrato(url, pergunta):
    r = perguntar(url, pergunta)
    assert r.status_code == 200
    assert validador("resposta").is_valid(r.json())
    assert r.json()["resposta"].startswith("[SIMULADO]")


def test_texto_tem_fonte_ficticia_e_nenhum_numero(url):
    texto = perguntar(url, "quanto ganha uma dev?").json()["resposta"]
    assert "[FONTE 1]" in texto
    assert not re.search(r"\d|R\$|%", texto.replace("[FONTE 1]", ""))


@pytest.mark.parametrize(
    ("pergunta", "aprovada", "bloqueada", "fora_de_escopo", "segundos"),
    [
        ("oi", True, False, False, []),
        ("antes #lento depois", True, False, False, [5.0]),
        ("x#bloqueada", False, True, False, []),
        ("#escopo?", False, False, True, []),
        ("#lento #bloqueada", False, True, False, [5.0]),
    ],
)
def test_simulador_modos(url, esperas, pergunta, aprovada, bloqueada, fora_de_escopo, segundos):
    corpo = perguntar(url, pergunta).json()
    assert (corpo["aprovada"], corpo["bloqueada"]) == (aprovada, bloqueada)
    assert corpo["fora_de_escopo"] is fora_de_escopo
    assert esperas == segundos


def test_simulador_modo_erro(url):
    r = perguntar(url, "dá #erro aqui")
    assert r.status_code == 500
    assert "#erro" not in r.text


async def test_agentes_http_fala_com_o_simulador(url):
    agentes = AgentesHttp(url, TOKEN)
    argumentos = {"sessao": "s", "historico": [Troca("p", "r" * 20_000)] * 3}
    try:
        r = await agentes.responder(pergunta="oi", lembranca=LEMBRANCA, **argumentos)
        assert r.resposta.startswith("[SIMULADO]") and r.aprovada
        with pytest.raises(AgentesIndisponiveis, match="500"):
            await agentes.responder(pergunta="#erro", lembranca=None, **argumentos)
    finally:
        await agentes.fechar()


def test_atende_outras_enquanto_uma_demora():
    livre = threading.Event()
    with simulador_no_ar(lambda _: livre.wait(10)) as url, ThreadPoolExecutor() as executor:
        lenta = executor.submit(perguntar, url, "#lento")
        try:
            assert perguntar(url, "rápida").status_code == 200
            assert not lenta.done()
        finally:
            livre.set()
        assert lenta.result().status_code == 200

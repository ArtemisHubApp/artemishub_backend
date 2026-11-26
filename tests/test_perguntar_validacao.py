import logging

import pytest

from tests.apoio.banco import linha, total_de_mensagens


@pytest.mark.parametrize(
    "pergunta", ["", "   \n\t ", "a" * 1001, " " * 600 + "a" + " " * 400, "zq\x00", 1, None, ["zq"]]
)
async def test_pergunta_vazia_e_longa(perguntar, sessao, conversa, agentes, pergunta):
    r = await perguntar(pergunta)
    assert r.status_code == 422
    assert agentes.chamadas == [] and await total_de_mensagens(sessao) == 0
    assert (await linha(sessao, conversa)).respondendo_desde is None


@pytest.mark.parametrize(
    "corpo",
    [
        b'{"pergunta": "zqx\\ud800"}',
        b'{"pergunta": "zqx\\u0000"}',
        b'{"pergunta": "' + b"zqx" * 400 + b'"}',
        b'{"pergunta": "zqx',
        b'"zqx"',
        b'{"texto": "zqx"}',
    ],
)
async def test_422_nao_repete_a_pergunta(cliente, ana, conversa, agentes, caplog, corpo):
    caplog.set_level(logging.DEBUG)
    cabecalho = {**ana, "Content-Type": "application/json"}
    r = await cliente.post(f"/v1/conversas/{conversa}/mensagens", headers=cabecalho, content=corpo)
    assert r.status_code == 422
    assert "zqx" not in r.text + caplog.text
    assert agentes.chamadas == []


async def test_pergunta_com_1000_caracteres_passa(perguntar):
    r = await perguntar("á" * 1000)
    assert r.status_code == 201 and r.json()["pergunta"]["texto"] == "á" * 1000

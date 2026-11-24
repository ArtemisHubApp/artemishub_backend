import asyncio
import logging
from datetime import UTC, datetime

import httpx
import pytest

from artemis_backend.adapters.agentes_http import AgentesHttp
from artemis_backend.adapters.banco import BancoIndisponivel, criar_fabrica_de_sessoes
from artemis_backend.adapters.repositorio_perguntas import RepositorioPerguntasSql
from artemis_backend.application.perguntar import AgentesIndisponiveis, ServicoPerguntas
from tests.apoio.banco import linha, mudar
from tests.apoio.conversas import LEMBRANCA, TEXTO_INDISPONIVEL


async def test_agentes_fora_do_ar(perguntar, mensagens, sessao, conversa, agentes):
    await mudar(sessao, conversa, lembranca=LEMBRANCA)
    agentes.erro = AgentesIndisponiveis()
    r = await perguntar()

    assert r.status_code == 201
    resposta = r.json()["resposta"]
    assert (resposta["texto"], resposta["aprovada"], resposta["bloqueada"]) == (
        TEXTO_INDISPONIVEL,
        False,
        False,
    )
    assert await mensagens() == [r.json()["pergunta"], resposta]
    depois = await linha(sessao, conversa)
    assert depois.respondendo_desde is None and depois.lembranca == LEMBRANCA
    assert len(agentes.chamadas) == 1  # sem nova tentativa
    agentes.erro = None
    assert (await perguntar()).status_code == 201


async def test_rota_com_agentes_http_respondendo_500(app, perguntar, mensagens, sessao, conversa):
    pedidos = []

    def atender(pedido):
        pedidos.append(pedido)
        return httpx.Response(500)

    agentes_http = AgentesHttp(
        "http://agentes.invalid", "token", transporte=httpx.MockTransport(atender)
    )
    repositorio = RepositorioPerguntasSql(criar_fabrica_de_sessoes(app.state.motor))
    app.state.perguntas = ServicoPerguntas(repositorio, agentes_http)
    r = await perguntar()
    await agentes_http.fechar()

    assert r.status_code == 201 and len(pedidos) == 1
    resposta = r.json()["resposta"]
    assert (resposta["texto"], resposta["aprovada"]) == (TEXTO_INDISPONIVEL, False)
    assert await mensagens() == [r.json()["pergunta"], resposta]
    assert (await linha(sessao, conversa)).respondendo_desde is None


async def test_excecao_inesperada_libera_a_trava_e_da_500(
    perguntar, mensagens, sessao, conversa, agentes, caplog
):
    caplog.set_level(logging.DEBUG)
    agentes.erro = RuntimeError("falha com zqx-pergunta")
    r = await perguntar("zqx-pergunta")
    assert (r.status_code, r.json()) == (500, {"detail": "Erro interno"})
    assert (await linha(sessao, conversa)).respondendo_desde is None
    assert [m["texto"] for m in await mensagens()] == ["zqx-pergunta"]
    assert "zqx" not in caplog.text


@pytest.mark.parametrize("cancelamentos", [1, 2])
async def test_cancelamento_libera_a_trava_e_propaga(
    perguntar, sessao, conversa, agentes, cancelamentos
):
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar())
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    for _ in range(cancelamentos):
        tarefa.cancel()
        await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        await tarefa
    async with asyncio.timeout(5):
        while (await linha(sessao, conversa)).respondendo_desde is not None:
            await asyncio.sleep(0.01)


async def test_excecao_nao_libera_trava_que_ja_e_de_outra(perguntar, sessao, conversa, agentes):
    agentes.bloquear()
    agentes.erro = RuntimeError("falha")
    tarefa = asyncio.create_task(perguntar())
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    nova = datetime.now(UTC)
    await mudar(sessao, conversa, respondendo_desde=nova)
    agentes.liberar()
    assert (await tarefa).status_code == 500
    assert (await linha(sessao, conversa)).respondendo_desde == nova


async def test_falha_ao_liberar_nao_esconde_o_erro_original(
    perguntar, agentes, monkeypatch, caplog
):
    async def quebra(*_):
        raise BancoIndisponivel

    monkeypatch.setattr(RepositorioPerguntasSql, "liberar_trava", quebra)
    agentes.erro = RuntimeError("falha")
    assert (await perguntar()).status_code == 500
    assert "RuntimeError" in caplog.text and "BancoIndisponivel" in caplog.text


async def test_falha_ao_gravar_a_resposta_libera_a_trava(
    app, perguntar, mensagens, sessao, conversa, monkeypatch
):
    async def quebra(*_, **__):
        raise BancoIndisponivel

    with monkeypatch.context() as m:
        m.setattr(RepositorioPerguntasSql, "concluir_pergunta", quebra)
        assert (await perguntar("p1")).status_code == 503
    assert (await linha(sessao, conversa)).respondendo_desde is None
    assert [m["texto"] for m in await mensagens()] == ["p1"]

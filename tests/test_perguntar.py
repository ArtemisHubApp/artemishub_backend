import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from artemis_backend.adapters.banco import criar_fabrica_de_sessoes
from artemis_backend.adapters.repositorio_perguntas import RepositorioPerguntasSql
from artemis_backend.adapters.tabelas import Mensagem
from artemis_backend.application.perguntar import AgentesIndisponiveis
from artemis_backend.domain.conversa import ConversaInexistente, NovaResposta
from tests.apoio.agentes import resposta_dos_agentes
from tests.apoio.banco import linha, mudar, total_de_mensagens
from tests.apoio.conversas import LEMBRANCA
from tests.apoio.valores import ANA, BIA

CAMPOS_DA_MENSAGEM = {
    "id",
    "papel",
    "texto",
    "criada_em",
    "aprovada",
    "bloqueada",
    "pergunta_id",
}


async def test_pergunta_grava_e_devolve_a_resposta(perguntar, mensagens, sessao, conversa, agentes):
    agentes.resposta = resposta_dos_agentes(resposta="Depende da UF.", trace_id="trace-1")
    r = await perguntar("  Quanto ganha uma dev?\n")

    assert r.status_code == 201
    assert set(r.json()) == {"pergunta", "resposta"}
    pergunta, resposta = r.json()["pergunta"], r.json()["resposta"]
    assert set(pergunta) == set(resposta) == CAMPOS_DA_MENSAGEM
    assert (pergunta["papel"], pergunta["texto"]) == ("usuaria", "Quanto ganha uma dev?")
    assert (resposta["papel"], resposta["texto"]) == ("artemis", "Depende da UF.")
    assert (resposta["aprovada"], resposta["bloqueada"]) == (True, False)
    assert pergunta["pergunta_id"] is None and resposta["pergunta_id"] == pergunta["id"]
    assert await mensagens() == [pergunta, resposta]
    assert await sessao.scalar(select(Mensagem.trace_id).where(Mensagem.papel == "artemis")) == (
        "trace-1"
    )
    assert (await linha(sessao, conversa)).respondendo_desde is None


async def test_nao_manda_email_nem_id_da_usuaria(perguntar, sessao, conversa, agentes):
    await perguntar("p1")
    await perguntar("p2")
    usuaria_id = str((await linha(sessao, conversa)).usuaria_id)
    enviado = json.dumps(agentes.chamadas, default=str)
    assert "p2" in enviado
    assert ANA not in enviado
    assert usuaria_id not in enviado and usuaria_id.replace("-", "") not in enviado


async def test_sem_token_responde_401(perguntar, agentes):
    assert (await perguntar(cabecalho={})).status_code == 401
    assert agentes.chamadas == []


async def test_perguntas_em_conversa_alheia(entrar_como, perguntar, sessao, conversa, agentes):
    bia = await entrar_como(BIA)
    alheia = await perguntar(cabecalho=bia)
    inexistente = await perguntar(cabecalho=bia, id_=str(uuid.uuid4()))
    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.json() == inexistente.json()
    # Ocupada também é 404 para quem não é dona: 409 revelaria que a conversa existe.
    await mudar(sessao, conversa, respondendo_desde=func.now())
    assert (await perguntar(cabecalho=bia)).status_code == 404
    assert (await perguntar(id_="nao-e-uuid")).status_code == 422
    assert agentes.chamadas == [] and await total_de_mensagens(sessao) == 0


async def test_repositorio_filtra_pela_dona_ao_concluir_e_liberar(
    app, entrar_como, perguntar, sessao, conversa, agentes
):
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar())
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    desde = (await linha(sessao, conversa)).respondendo_desde
    repositorio = RepositorioPerguntasSql(criar_fabrica_de_sessoes(app.state.motor))
    outra, id_ = uuid.uuid4(), uuid.UUID(conversa)
    await repositorio.liberar_trava(outra, id_, desde)
    resposta = NovaResposta(uuid.uuid4(), "intrusa", True, False, None, None)
    with pytest.raises(ConversaInexistente):
        await repositorio.concluir_pergunta(outra, id_, desde, resposta, LEMBRANCA)
    assert await total_de_mensagens(sessao) == 1
    assert (await linha(sessao, conversa)).respondendo_desde == desde
    agentes.liberar()
    assert (await tarefa).status_code == 201


async def test_titulo_vem_so_da_primeira_pergunta(cliente, ana, perguntar, conversa):
    await perguntar("  Primeira\npergunta " + "palavra " * 20)
    detalhe = (await cliente.get(f"/v1/conversas/{conversa}", headers=ana)).json()
    assert detalhe["titulo"].startswith("Primeira pergunta palavra")
    assert len(detalhe["titulo"]) <= 60
    await perguntar("Segunda")
    depois = (await cliente.get(f"/v1/conversas/{conversa}", headers=ana)).json()
    assert depois["titulo"] == detalhe["titulo"]


async def test_atualizada_em_muda_na_pergunta_e_na_resposta(perguntar, sessao, conversa, agentes):
    await mudar(sessao, conversa, atualizada_em=datetime(2026, 1, 1, tzinfo=UTC))
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar())
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    na_pergunta = (await linha(sessao, conversa)).atualizada_em
    assert na_pergunta > datetime(2026, 1, 1, tzinfo=UTC)
    agentes.liberar()
    await tarefa
    assert (await linha(sessao, conversa)).atualizada_em > na_pergunta


async def test_logs_sem_texto_email_nem_token(perguntar, ana, agentes, caplog):
    caplog.set_level(logging.INFO)
    agentes.resposta = resposta_dos_agentes(resposta="zqx-resposta", trace_id="zqx-trace")
    await perguntar("zqx-pergunta")
    agentes.erro = AgentesIndisponiveis()
    await perguntar("zqx-pergunta")
    token = ana["Authorization"].removeprefix("Bearer ")
    assert not any(t in caplog.text for t in ("zqx", ANA, token))

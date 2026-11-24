import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text, update

from artemis_backend.adapters.agentes_http import AgentesHttp
from artemis_backend.adapters.banco import BancoIndisponivel, criar_fabrica_de_sessoes
from artemis_backend.adapters.repositorio_conversas import RepositorioConversasSql
from artemis_backend.adapters.tabelas import Conversa, Mensagem, Usuaria
from artemis_backend.application.perguntar import AgentesIndisponiveis, ServicoPerguntas
from artemis_backend.domain.conversa import ConversaInexistente, NovaResposta, Troca
from tests.conftest import resposta_dos_agentes

ANA = "ana@example.com"
BIA = "bia@example.com"
TEXTO_INDISPONIVEL = "Não consegui responder agora, tente de novo"
CAMPOS_DA_MENSAGEM = {
    "id",
    "papel",
    "texto",
    "criada_em",
    "aprovada",
    "bloqueada",
    "pergunta_id",
}
LEMBRANCA = {
    "salario": True,
    "direitos": False,
    "cbo_familia": "2124",
    "cbo_familia_nome": "Analistas",
    "ocupacao": None,
    "uf": "SP",
}
OUTRA = {**LEMBRANCA, "uf": "RJ"}


@pytest_asyncio.fixture
async def sessao(app):
    async with criar_fabrica_de_sessoes(app.state.motor)() as s:
        yield s


@pytest_asyncio.fixture
async def ana(entrar_como):
    return await entrar_como(ANA)


@pytest_asyncio.fixture
async def conversa(cliente, ana) -> str:
    return (await cliente.post("/v1/conversas", headers=ana)).json()["id"]


@pytest.fixture
def perguntar(cliente, ana, conversa):
    async def enviar(pergunta="Quanto ganha uma dev?", id_=conversa, cabecalho=ana):
        return await cliente.post(
            f"/v1/conversas/{id_}/mensagens", headers=cabecalho, json={"pergunta": pergunta}
        )

    return enviar


@pytest.fixture
def mensagens(cliente, ana, conversa):
    async def ler() -> list[dict]:
        return (await cliente.get(f"/v1/conversas/{conversa}", headers=ana)).json()["mensagens"]

    return ler


async def linha(sessao, conversa: str) -> Conversa | None:
    await sessao.rollback()
    return await sessao.scalar(
        select(Conversa)
        .where(Conversa.id == uuid.UUID(conversa))
        .execution_options(populate_existing=True)
    )


async def mudar(sessao, conversa: str, **valores) -> None:
    await sessao.execute(
        update(Conversa).where(Conversa.id == uuid.UUID(conversa)).values(**valores)
    )
    await sessao.commit()


async def total_de_mensagens(sessao) -> int:
    await sessao.rollback()
    return await sessao.scalar(select(func.count()).select_from(Mensagem))


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


async def test_nao_manda_email_nem_id_da_usuaria(perguntar, sessao, conversa, agentes):
    await perguntar("p1")
    await perguntar("p2")
    usuaria_id = str((await linha(sessao, conversa)).usuaria_id)
    enviado = json.dumps(agentes.chamadas, default=str)
    assert "p2" in enviado
    assert ANA not in enviado
    assert usuaria_id not in enviado and usuaria_id.replace("-", "") not in enviado


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


async def test_sem_token_responde_401(perguntar, agentes):
    assert (await perguntar(cabecalho={})).status_code == 401
    assert agentes.chamadas == []


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


async def test_trava_recente_responde_409(perguntar, sessao, conversa, agentes):
    await mudar(sessao, conversa, respondendo_desde=func.now() - timedelta(seconds=50))
    antes = (await linha(sessao, conversa)).respondendo_desde
    r = await perguntar()
    assert r.status_code == 409 and agentes.chamadas == []
    assert (await linha(sessao, conversa)).respondendo_desde == antes
    assert await total_de_mensagens(sessao) == 0


async def test_trava_velha_expira(perguntar, sessao, conversa):
    await mudar(sessao, conversa, respondendo_desde=func.now() - timedelta(seconds=61))
    assert (await perguntar()).status_code == 201
    assert (await linha(sessao, conversa)).respondendo_desde is None


async def test_duas_perguntas_disputam_a_trava_velha(perguntar, sessao, conversa, agentes):
    await mudar(sessao, conversa, respondendo_desde=func.now() - timedelta(seconds=61))
    agentes.bloquear()
    tarefas = [asyncio.create_task(perguntar(f"p{i}")) for i in range(2)]
    prontas, presas = await asyncio.wait(tarefas, timeout=10, return_when=asyncio.FIRST_COMPLETED)
    assert [t.result().status_code for t in prontas] == [409]
    agentes.liberar()
    assert (await presas.pop()).status_code == 201


async def test_trava_tomada_por_outra_descarta_a_resposta_tardia(
    perguntar, mensagens, sessao, conversa, agentes
):
    agentes.resposta = resposta_dos_agentes(resposta="tardia", lembranca=LEMBRANCA)
    agentes.bloquear()
    tarefa = asyncio.create_task(perguntar("lenta"))
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    nova = datetime.now(UTC)
    await mudar(sessao, conversa, respondendo_desde=nova)
    agentes.liberar()

    assert (await tarefa).status_code == 409
    assert [m["texto"] for m in await mensagens()] == ["lenta"]
    depois = await linha(sessao, conversa)
    assert depois.respondendo_desde == nova and depois.lembranca is None


async def test_trava_expirada_tomada_e_ja_concluida_descarta_a_tardia(
    perguntar, mensagens, sessao, conversa, agentes
):
    agentes.bloquear()
    lenta = asyncio.create_task(perguntar("lenta"))
    await asyncio.wait_for(agentes.chamado.wait(), 10)
    await mudar(sessao, conversa, respondendo_desde=func.now() - timedelta(seconds=61))
    rapida = asyncio.create_task(perguntar("rápida"))
    async with asyncio.timeout(10):
        while len(agentes.chamadas) < 2:
            await asyncio.sleep(0.01)
    agentes.liberar()
    assert sorted([(await lenta).status_code, (await rapida).status_code]) == [201, 409]
    assert (await rapida).status_code == 201
    assert [m["texto"] for m in await mensagens()] == ["lenta", "rápida", agentes.resposta.resposta]


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


async def test_trava_vencida_e_nao_tomada_ainda_grava_a_resposta(app, sessao, conversa):
    desde = datetime.now(UTC) - timedelta(seconds=61)
    await mudar(sessao, conversa, respondendo_desde=desde)
    dona = (await linha(sessao, conversa)).usuaria_id
    repositorio = RepositorioConversasSql(criar_fabrica_de_sessoes(app.state.motor))
    resposta = NovaResposta(uuid.uuid4(), "no limite", False, False, None, None)
    gravada = await repositorio.concluir_pergunta(dona, uuid.UUID(conversa), desde, resposta, None)
    assert gravada.texto == "no limite"
    assert await total_de_mensagens(sessao) == 1
    assert (await linha(sessao, conversa)).respondendo_desde is None


async def test_rota_com_agentes_http_respondendo_500(app, perguntar, mensagens, sessao, conversa):
    pedidos = []

    def atender(pedido):
        pedidos.append(pedido)
        return httpx.Response(500)

    agentes_http = AgentesHttp(
        "http://agentes.invalid", "token", transporte=httpx.MockTransport(atender)
    )
    repositorio = RepositorioConversasSql(criar_fabrica_de_sessoes(app.state.motor))
    app.state.perguntas = ServicoPerguntas(repositorio, agentes_http)
    r = await perguntar()
    await agentes_http.fechar()

    assert r.status_code == 201 and len(pedidos) == 1
    resposta = r.json()["resposta"]
    assert (resposta["texto"], resposta["aprovada"]) == (TEXTO_INDISPONIVEL, False)
    assert await mensagens() == [r.json()["pergunta"], resposta]
    assert (await linha(sessao, conversa)).respondendo_desde is None


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
    repositorio = RepositorioConversasSql(criar_fabrica_de_sessoes(app.state.motor))
    outra, id_ = uuid.uuid4(), uuid.UUID(conversa)
    await repositorio.liberar_trava(outra, id_, desde)
    resposta = NovaResposta(uuid.uuid4(), "intrusa", True, False, None, None)
    with pytest.raises(ConversaInexistente):
        await repositorio.concluir_pergunta(outra, id_, desde, resposta, LEMBRANCA)
    assert await total_de_mensagens(sessao) == 1
    assert (await linha(sessao, conversa)).respondendo_desde == desde
    agentes.liberar()
    assert (await tarefa).status_code == 201


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

    monkeypatch.setattr(RepositorioConversasSql, "liberar_trava", quebra)
    agentes.erro = RuntimeError("falha")
    assert (await perguntar()).status_code == 500
    assert "RuntimeError" in caplog.text and "BancoIndisponivel" in caplog.text


async def test_falha_ao_gravar_a_resposta_libera_a_trava(
    app, perguntar, mensagens, sessao, conversa, monkeypatch
):
    async def quebra(*_, **__):
        raise BancoIndisponivel

    with monkeypatch.context() as m:
        m.setattr(RepositorioConversasSql, "concluir_pergunta", quebra)
        assert (await perguntar("p1")).status_code == 503
    assert (await linha(sessao, conversa)).respondendo_desde is None
    assert [m["texto"] for m in await mensagens()] == ["p1"]


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

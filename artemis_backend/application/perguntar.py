import asyncio
import logging
import uuid
from datetime import datetime

from artemis_backend.application.portas import (
    Agentes,
    AgentesIndisponiveis,
    RepositorioPerguntas,
    RespostaAgentes,
)
from artemis_backend.domain.conversa import (
    ConversaInexistente,
    ConversaOcupada,
    Mensagem,
    NovaResposta,
    PerguntaIniciada,
    memoria_curta,
    titulo_da_conversa,
)

_log = logging.getLogger(__name__)

TEXTO_INDISPONIVEL = "Não consegui responder agora, tente de novo"
_INDISPONIVEL = RespostaAgentes(
    resposta=TEXTO_INDISPONIVEL,
    aprovada=False,
    bloqueada=False,
    fora_de_escopo=False,
    lembranca=None,
    trace_id=None,
)


class ServicoPerguntas:
    def __init__(self, repositorio: RepositorioPerguntas, agentes: Agentes) -> None:
        self._repositorio = repositorio
        self._agentes = agentes
        # Referência forte: o laço de eventos só guarda referência fraca das tarefas.
        self._liberacoes: set[asyncio.Task[None]] = set()

    async def perguntar(
        self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID, pergunta: str
    ) -> tuple[Mensagem, Mensagem]:
        """Grava a pergunta, chama os agentes sem segurar o banco e grava a resposta."""
        pergunta = pergunta.strip()
        iniciada = await self._repositorio.iniciar_pergunta(
            usuaria_id, conversa_id, uuid.uuid4(), pergunta, titulo_da_conversa(pergunta)
        )
        try:
            obtida = await self._responder(conversa_id, iniciada)
            resposta = await self._concluir(usuaria_id, conversa_id, iniciada, obtida)
        except (ConversaInexistente, ConversaOcupada):
            raise  # a trava já não é desta pergunta
        except BaseException:
            # BaseException inclui o cancelamento (desligamento da API).
            await self._liberar(usuaria_id, conversa_id, iniciada.respondendo_desde)
            raise
        return iniciada.pergunta, resposta

    async def _responder(
        self, conversa_id: uuid.UUID, iniciada: PerguntaIniciada
    ) -> RespostaAgentes:
        try:
            return await self._agentes.responder(
                pergunta=iniciada.pergunta.texto,
                sessao=str(conversa_id),
                historico=memoria_curta(list(iniciada.anteriores)),
                lembranca=iniciada.lembranca,
            )
        except AgentesIndisponiveis:
            return _INDISPONIVEL

    async def _concluir(
        self,
        usuaria_id: uuid.UUID,
        conversa_id: uuid.UUID,
        iniciada: PerguntaIniciada,
        obtida: RespostaAgentes,
    ) -> Mensagem:
        # Só resposta aprovada entra na memória curta: bloqueada e fora de escopo nunca.
        aceita = not (obtida.bloqueada or obtida.fora_de_escopo)
        resposta = NovaResposta(
            id=uuid.uuid4(),
            texto=obtida.resposta,
            aprovada=obtida.aprovada and aceita,
            bloqueada=obtida.bloqueada,
            trace_id=obtida.trace_id,
            pergunta_id=iniciada.pergunta.id,
        )
        return await self._repositorio.concluir_pergunta(
            usuaria_id,
            conversa_id,
            iniciada.respondendo_desde,
            resposta,
            obtida.lembranca if aceita else None,
        )

    async def _liberar(
        self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID, respondendo_desde: datetime
    ) -> None:
        async def liberar() -> None:
            try:
                await self._repositorio.liberar_trava(usuaria_id, conversa_id, respondendo_desde)
            except Exception as erro:
                # A trava expira sozinha; o erro que importa é o que está se propagando.
                _log.error("Trava não liberada: %s", type(erro).__name__)

        # Protegida: um novo cancelamento não pode interromper a liberação.
        tarefa = asyncio.create_task(liberar())
        self._liberacoes.add(tarefa)
        tarefa.add_done_callback(self._liberacoes.discard)
        await asyncio.shield(tarefa)

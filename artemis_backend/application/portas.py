import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from artemis_backend.domain.conversa import (
    Conversa,
    ConversaComMensagens,
    Mensagem,
    NovaResposta,
    PerguntaIniciada,
    Troca,
)


class AgentesIndisponiveis(Exception):
    """Os agentes não responderam a tempo ou responderam fora do contrato."""


@dataclass(frozen=True)
class RespostaAgentes:
    resposta: str
    aprovada: bool
    bloqueada: bool
    fora_de_escopo: bool
    lembranca: dict[str, Any] | None
    trace_id: str | None


class Agentes(Protocol):
    async def responder(
        self,
        pergunta: str,
        sessao: str,
        historico: list[Troca],
        lembranca: dict[str, Any] | None,
    ) -> RespostaAgentes:
        """Levanta AgentesIndisponiveis. Nunca recebe e-mail nem id da usuária."""


class RepositorioConversas(Protocol):
    """Toda consulta recebe `usuaria_id`: conversa de outra usuária é como se não existisse."""

    async def criar(self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID) -> Conversa: ...

    async def listar(self, usuaria_id: uuid.UUID) -> list[Conversa]:
        """Da mais recente para a mais antiga, com desempate fixo."""

    async def obter(
        self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID
    ) -> ConversaComMensagens | None:
        """Mensagens em ordem cronológica, a pergunta antes da resposta nos empates."""

    async def apagar(self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID) -> bool:
        """Apaga a conversa e as mensagens; False se não existe (ou já foi apagada)."""

    async def iniciar_pergunta(
        self,
        usuaria_id: uuid.UUID,
        conversa_id: uuid.UUID,
        pergunta_id: uuid.UUID,
        texto: str,
        titulo: str,
    ) -> PerguntaIniciada:
        """Pega a trava e grava a pergunta, tudo ou nada; o título só vale se ainda não há um.

        Levanta ConversaInexistente ou, se outra pergunta está em andamento, ConversaOcupada.
        """

    async def concluir_pergunta(
        self,
        usuaria_id: uuid.UUID,
        conversa_id: uuid.UUID,
        respondendo_desde: datetime,
        resposta: NovaResposta,
        lembranca: dict[str, Any] | None,
    ) -> Mensagem:
        """Grava a resposta e solta a trava, tudo ou nada; `lembranca` None mantém a atual.

        Sem a trava obtida em `respondendo_desde`, não grava nada: ConversaInexistente se a
        conversa sumiu, ConversaOcupada se a trava expirou e passou para outra pergunta.
        """

    async def liberar_trava(
        self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID, respondendo_desde: datetime
    ) -> None:
        """Solta a trava só se ela ainda é a obtida em `respondendo_desde`."""

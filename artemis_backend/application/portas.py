import uuid
from typing import Protocol

from artemis_backend.domain.conversa import Conversa, ConversaComMensagens


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

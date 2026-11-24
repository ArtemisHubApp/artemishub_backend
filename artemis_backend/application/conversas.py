import uuid

from artemis_backend.application.portas import RepositorioConversas
from artemis_backend.domain.conversa import Conversa, ConversaComMensagens, ConversaInexistente


class ServicoConversas:
    def __init__(self, repositorio: RepositorioConversas) -> None:
        self._repositorio = repositorio

    async def criar(self, usuaria_id: uuid.UUID) -> Conversa:
        return await self._repositorio.criar(usuaria_id, uuid.uuid4())

    async def listar(self, usuaria_id: uuid.UUID) -> list[Conversa]:
        return await self._repositorio.listar(usuaria_id)

    async def obter(self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID) -> ConversaComMensagens:
        historico = await self._repositorio.obter(usuaria_id, conversa_id)
        if historico is None:
            raise ConversaInexistente
        return historico

    async def apagar(self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID) -> None:
        if not await self._repositorio.apagar(usuaria_id, conversa_id):
            raise ConversaInexistente

    async def apagar_todas(self, usuaria_id: uuid.UUID) -> None:
        await self._repositorio.apagar_todas(usuaria_id)

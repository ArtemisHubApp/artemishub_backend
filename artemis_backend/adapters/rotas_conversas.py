import dataclasses
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, PlainSerializer

from artemis_backend.adapters.rotas_auth import usuaria_atual
from artemis_backend.application.conversas import ServicoConversas
from artemis_backend.domain.conversa import ConversaInexistente

roteador = APIRouter(prefix="/v1/conversas", tags=["conversas"])


def _em_utc(data: datetime) -> str:
    return data.astimezone(UTC).isoformat().replace("+00:00", "Z")


DataUtc = Annotated[datetime, PlainSerializer(_em_utc, return_type=str)]


class ConversaSaida(BaseModel):
    id: uuid.UUID
    titulo: str | None
    criada_em: DataUtc
    atualizada_em: DataUtc


class MensagemSaida(BaseModel):
    id: uuid.UUID
    papel: str
    texto: str
    criada_em: DataUtc
    aprovada: bool
    bloqueada: bool
    pergunta_id: uuid.UUID | None


class ConversaDetalheSaida(ConversaSaida):
    mensagens: list[MensagemSaida]


def _servico(request: Request) -> ServicoConversas:
    return request.app.state.conversas


Servico = Annotated[ServicoConversas, Depends(_servico)]
Usuaria = Annotated[uuid.UUID, Depends(usuaria_atual)]


def _nao_encontrada() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada")


@roteador.get("", response_model=list[ConversaSaida])
async def listar(usuaria_id: Usuaria, servico: Servico):
    return await servico.listar(usuaria_id)


@roteador.post("", status_code=status.HTTP_201_CREATED, response_model=ConversaSaida)
async def criar(usuaria_id: Usuaria, servico: Servico):
    return await servico.criar(usuaria_id)


@roteador.get("/{conversa_id}", response_model=ConversaDetalheSaida)
async def detalhar(conversa_id: uuid.UUID, usuaria_id: Usuaria, servico: Servico):
    try:
        historico = await servico.obter(usuaria_id, conversa_id)
    except ConversaInexistente:
        raise _nao_encontrada() from None
    return {**dataclasses.asdict(historico.conversa), "mensagens": historico.mensagens}


@roteador.delete("/{conversa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar(conversa_id: uuid.UUID, usuaria_id: Usuaria, servico: Servico) -> Response:
    try:
        await servico.apagar(usuaria_id, conversa_id)
    except ConversaInexistente:
        raise _nao_encontrada() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)

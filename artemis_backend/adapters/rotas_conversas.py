import dataclasses
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, PlainSerializer, StrictStr, field_validator

from artemis_backend.adapters.rotas_auth import token_invalido, usuaria_atual
from artemis_backend.application.conversas import ServicoConversas
from artemis_backend.application.perguntar import ServicoPerguntas
from artemis_backend.domain.conversa import (
    PERGUNTA_MAXIMA,
    ConversaInexistente,
    ConversaOcupada,
    UsuariaInexistente,
)

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


class PedidoPergunta(BaseModel):
    # O limite vale para o texto como chegou; surrogate solto o próprio pydantic recusa.
    pergunta: StrictStr = Field(max_length=PERGUNTA_MAXIMA)

    @field_validator("pergunta")
    @classmethod
    def _recusar_vazia_e_nul(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("A pergunta não pode ser vazia")
        if "\x00" in valor:
            raise ValueError("A pergunta tem um caractere inválido")
        return valor


class PerguntaRespondidaSaida(BaseModel):
    pergunta: MensagemSaida
    resposta: MensagemSaida


def _servico(request: Request) -> ServicoConversas:
    return request.app.state.conversas


def _perguntas(request: Request) -> ServicoPerguntas:
    return request.app.state.perguntas


Servico = Annotated[ServicoConversas, Depends(_servico)]
Perguntas = Annotated[ServicoPerguntas, Depends(_perguntas)]
Usuaria = Annotated[uuid.UUID, Depends(usuaria_atual)]


def _nao_encontrada() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada")


@roteador.get("", response_model=list[ConversaSaida])
async def listar(usuaria_id: Usuaria, servico: Servico):
    return await servico.listar(usuaria_id)


@roteador.post("", status_code=status.HTTP_201_CREATED, response_model=ConversaSaida)
async def criar(usuaria_id: Usuaria, servico: Servico):
    try:
        return await servico.criar(usuaria_id)
    except UsuariaInexistente:
        # Conta apagada entre a checagem do token e a gravação: igual a um token inválido.
        raise token_invalido() from None


@roteador.get("/{conversa_id}", response_model=ConversaDetalheSaida)
async def detalhar(conversa_id: uuid.UUID, usuaria_id: Usuaria, servico: Servico):
    try:
        historico = await servico.obter(usuaria_id, conversa_id)
    except ConversaInexistente:
        raise _nao_encontrada() from None
    return {**dataclasses.asdict(historico.conversa), "mensagens": historico.mensagens}


@roteador.post(
    "/{conversa_id}/mensagens",
    status_code=status.HTTP_201_CREATED,
    response_model=PerguntaRespondidaSaida,
)
async def perguntar(
    conversa_id: uuid.UUID, pedido: PedidoPergunta, usuaria_id: Usuaria, servico: Perguntas
):
    try:
        pergunta, resposta = await servico.perguntar(usuaria_id, conversa_id, pedido.pergunta)
    except ConversaInexistente:
        raise _nao_encontrada() from None
    except ConversaOcupada:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já há uma pergunta em andamento nesta conversa"
        ) from None
    return {"pergunta": pergunta, "resposta": resposta}


@roteador.delete("/{conversa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar(conversa_id: uuid.UUID, usuaria_id: Usuaria, servico: Servico) -> Response:
    try:
        await servico.apagar(usuaria_id, conversa_id)
    except ConversaInexistente:
        raise _nao_encontrada() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)

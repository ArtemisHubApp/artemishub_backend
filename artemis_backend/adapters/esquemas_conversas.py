import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, StrictStr, field_validator

from artemis_backend.domain.conversa import PERGUNTA_MAXIMA


def _em_utc(data: datetime) -> str:
    return data.astimezone(UTC).isoformat().replace("+00:00", "Z")


DataUtc = Annotated[datetime, PlainSerializer(_em_utc, return_type=str)]


class ConversaSaida(BaseModel):
    id: uuid.UUID
    titulo: str | None
    criada_em: DataUtc
    atualizada_em: DataUtc


class PaginaDeConversasSaida(BaseModel):
    itens: list[ConversaSaida]
    proximo: str | None


class MensagemSaida(BaseModel):
    id: uuid.UUID
    papel: Literal["usuaria", "artemis"]
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


Motivo = Literal["ocupada", "expirada"]


class ErroDeConflito(BaseModel):
    """`ocupada`: a pergunta não foi gravada. `expirada`: foi, mas a resposta se perdeu."""

    detail: str
    codigo: Motivo

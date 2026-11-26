import uuid
from typing import Literal

from pydantic import BaseModel, Field, StrictBool, field_validator

from artemis_backend.domain.usuaria import (
    SENHA_MAXIMA,
    SENHA_MINIMA,
    EmailInvalido,
    normalizar_email,
)


def _email_valido(email: str) -> str:
    try:
        return normalizar_email(email)
    except EmailInvalido as erro:
        raise ValueError(str(erro)) from None


class _PedidoComEmail(BaseModel):
    email: str

    _normalizar = field_validator("email")(_email_valido)


class PedidoCadastro(_PedidoComEmail):
    senha: str = Field(min_length=SENHA_MINIMA, max_length=SENHA_MAXIMA)
    consentimento: StrictBool

    @field_validator("consentimento")
    @classmethod
    def _exigir_consentimento(cls, valor: bool) -> bool:
        if not valor:
            raise ValueError("O consentimento é obrigatório")
        return valor


class PedidoLogin(_PedidoComEmail):
    # Sem mínimo: senha curta é só senha errada. O máximo evita gastar CPU com entrada enorme.
    senha: str = Field(max_length=SENHA_MAXIMA)


class CadastroSaida(BaseModel):
    id: uuid.UUID


class LoginSaida(BaseModel):
    token: str
    tipo: Literal["bearer"]


class ContaSaida(BaseModel):
    id: uuid.UUID
    email: str


class ConsentimentoSaida(BaseModel):
    texto: str

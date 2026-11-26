import uuid
from typing import Literal

from pydantic import BaseModel, Field, StrictBool, field_validator

from artemis_backend.domain.usuaria import (
    NOME_MAXIMO,
    SENHA_MAXIMA,
    SENHA_MINIMA,
    EmailInvalido,
    NomeInvalido,
    Usuaria,
    normalizar_email,
    normalizar_nome,
)


def _email_valido(email: str) -> str:
    try:
        return normalizar_email(email)
    except EmailInvalido as erro:
        raise ValueError(str(erro)) from None


def _nome_valido(nome: str) -> str:
    try:
        return normalizar_nome(nome)
    except NomeInvalido as erro:
        raise ValueError(str(erro)) from None


class PedidoNome(BaseModel):
    nome: str = Field(
        description=(
            "Como a usuária quer ser chamada (só o primeiro nome ou apelido). De 1 a "
            f"{NOME_MAXIMO} caracteres, contados depois de tirar os espaços das pontas e "
            "reduzir os repetidos."
        ),
        json_schema_extra={"minLength": 1, "maxLength": NOME_MAXIMO},
    )

    _normalizar_nome = field_validator("nome")(_nome_valido)


class _PedidoComEmail(BaseModel):
    email: str

    _normalizar = field_validator("email")(_email_valido)


class PedidoCadastro(PedidoNome, _PedidoComEmail):
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
    nome: str
    email: str

    @classmethod
    def de(cls, usuaria: Usuaria) -> "ContaSaida":
        return cls(id=usuaria.id, nome=usuaria.nome, email=usuaria.email)


class ConsentimentoSaida(BaseModel):
    texto: str

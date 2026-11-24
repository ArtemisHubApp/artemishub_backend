import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, StrictBool, field_validator

from artemis_backend.application.contas import ServicoContas
from artemis_backend.domain.usuaria import (
    SENHA_MAXIMA,
    SENHA_MINIMA,
    ConsentimentoAusente,
    CredenciaisInvalidas,
    EmailInvalido,
    EmailJaCadastrado,
    TokenInvalido,
    normalizar_email,
)

roteador = APIRouter(prefix="/v1/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


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


def _servico(request: Request) -> ServicoContas:
    return request.app.state.contas


Servico = Annotated[ServicoContas, Depends(_servico)]


@roteador.post("/cadastro", status_code=status.HTTP_201_CREATED)
async def cadastro(pedido: PedidoCadastro, servico: Servico) -> dict[str, str]:
    try:
        id_ = await servico.cadastrar(pedido.email, pedido.senha, pedido.consentimento)
    except EmailJaCadastrado:
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado") from None
    except (ConsentimentoAusente, EmailInvalido) as erro:
        raise HTTPException(422, str(erro)) from None
    return {"id": str(id_)}


@roteador.post("/login")
async def login(pedido: PedidoLogin, servico: Servico) -> dict[str, str]:
    try:
        token = await servico.entrar(pedido.email, pedido.senha)
    except CredenciaisInvalidas:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return {"token": token, "tipo": "bearer"}


def token_invalido() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Token inválido ou vencido",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def usuaria_atual(
    servico: Servico,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    """Id da usuária do token; 401 se faltar, for inválido, vencido ou de usuária inexistente."""
    try:
        if credenciais is None:
            raise TokenInvalido
        return await servico.usuaria_do_token(credenciais.credentials)
    except TokenInvalido:
        raise token_invalido() from None

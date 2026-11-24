"""Quem está pedindo: do `Authorization` ou do cookie à usuária."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from artemis_backend.adapters.origem import exigir_origem_sem_authorization
from artemis_backend.adapters.sessao import cookies_de_sessao
from artemis_backend.application.contas import ServicoContas
from artemis_backend.domain.usuaria import TokenInvalido

_bearer = HTTPBearer(auto_error=False)


def _servico(request: Request) -> ServicoContas:
    return request.app.state.contas


Contas = Annotated[ServicoContas, Depends(_servico)]


def token_invalido() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Token inválido ou vencido",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _token_do_pedido(request: Request, credenciais: HTTPAuthorizationCredentials | None) -> str:
    """`Authorization`, mesmo malformado, vence o cookie; repetido, nenhum dos dois vale."""
    autorizacoes = request.headers.getlist("authorization")
    if autorizacoes:
        tokens = [credenciais.credentials] if credenciais and len(autorizacoes) == 1 else []
    else:
        tokens = cookies_de_sessao(request)
    if len(tokens) != 1:
        raise TokenInvalido
    return tokens[0]


async def usuaria_atual(
    request: Request,
    _origem: Annotated[None, Depends(exigir_origem_sem_authorization)],
    contas: Contas,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    """Id da usuária do token; 401 se faltar, for inválido, vencido ou de usuária inexistente."""
    try:
        return await contas.usuaria_do_token(_token_do_pedido(request, credenciais))
    except TokenInvalido:
        raise token_invalido() from None


Usuaria = Annotated[uuid.UUID, Depends(usuaria_atual)]

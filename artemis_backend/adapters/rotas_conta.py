import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from artemis_backend.adapters.rotas_auth import Servico, token_invalido, usuaria_atual
from artemis_backend.adapters.sessao import apagar_cookie
from artemis_backend.domain.usuaria import CONSENTIMENTO, TokenInvalido

roteador = APIRouter(tags=["conta"])
Usuaria = Annotated[uuid.UUID, Depends(usuaria_atual)]


@roteador.get("/v1/consentimento")
async def consentimento() -> dict[str, str]:
    """Pública: a pessoa lê o texto antes de se cadastrar."""
    return {"texto": CONSENTIMENTO}


@roteador.get("/v1/conta")
async def ver(usuaria_id: Usuaria, servico: Servico) -> dict[str, str]:
    try:
        usuaria = await servico.obter(usuaria_id)
    except TokenInvalido:
        raise token_invalido() from None
    return {"id": str(usuaria.id), "email": usuaria.email}


@roteador.delete("/v1/conta", status_code=status.HTTP_204_NO_CONTENT)
async def excluir(usuaria_id: Usuaria, servico: Servico, request: Request) -> Response:
    """Apaga a conta do token e, em cascata, as conversas e mensagens dela."""
    try:
        await servico.excluir(usuaria_id)
    except TokenInvalido:
        raise token_invalido() from None
    resposta = Response(status_code=status.HTTP_204_NO_CONTENT)
    apagar_cookie(request, resposta)
    return resposta

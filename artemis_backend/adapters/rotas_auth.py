from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from artemis_backend.adapters.autenticacao import Contas
from artemis_backend.adapters.esquemas_auth import PedidoCadastro, PedidoLogin
from artemis_backend.adapters.origem import exigir_origem_com_cookie, recusar_outra_origem
from artemis_backend.adapters.sessao import apagar_cookie, cookies_de_sessao, gravar_cookie
from artemis_backend.domain.usuaria import (
    ConsentimentoAusente,
    CredenciaisInvalidas,
    EmailInvalido,
    EmailJaCadastrado,
)

roteador = APIRouter(prefix="/v1/auth", tags=["auth"])


@roteador.post(
    "/cadastro",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(recusar_outra_origem)],
)
async def cadastro(pedido: PedidoCadastro, contas: Contas) -> dict[str, str]:
    try:
        id_ = await contas.cadastrar(pedido.email, pedido.senha, pedido.consentimento)
    except EmailJaCadastrado:
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado") from None
    except (ConsentimentoAusente, EmailInvalido) as erro:
        raise HTTPException(422, str(erro)) from None
    return {"id": str(id_)}


@roteador.post("/login", dependencies=[Depends(recusar_outra_origem)])
async def login(
    pedido: PedidoLogin, contas: Contas, request: Request, resposta: Response
) -> dict[str, str]:
    try:
        token = await contas.entrar(pedido.email, pedido.senha)
    except CredenciaisInvalidas:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    gravar_cookie(request, resposta, token)
    return {"token": token, "tipo": "bearer"}


@roteador.post(
    "/sair",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(exigir_origem_com_cookie)],
)
async def sair(request: Request) -> Response:
    resposta = Response(status_code=status.HTTP_204_NO_CONTENT)
    # Formulário de outro site chega sem o cookie (SameSite) e não pode encerrar a sessão.
    if cookies_de_sessao(request):
        apagar_cookie(request, resposta)
    return resposta

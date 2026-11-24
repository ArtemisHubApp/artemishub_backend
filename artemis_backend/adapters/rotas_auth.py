from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from artemis_backend.adapters.autenticacao import Contas
from artemis_backend.adapters.esquemas_auth import (
    CadastroSaida,
    LoginSaida,
    PedidoCadastro,
    PedidoLogin,
)
from artemis_backend.adapters.esquemas_de_erro import erros
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
    responses=erros(403, 409, 422, 503),
)
async def cadastro(pedido: PedidoCadastro, contas: Contas) -> CadastroSaida:
    try:
        id_ = await contas.cadastrar(pedido.email, pedido.senha, pedido.consentimento)
    except EmailJaCadastrado:
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado") from None
    except (ConsentimentoAusente, EmailInvalido) as erro:
        raise HTTPException(422, str(erro)) from None
    return CadastroSaida(id=id_)


@roteador.post(
    "/login",
    dependencies=[Depends(recusar_outra_origem)],
    responses=erros(401, 403, 422, 503),
)
async def login(
    pedido: PedidoLogin, contas: Contas, request: Request, resposta: Response
) -> LoginSaida:
    try:
        token = await contas.entrar(pedido.email, pedido.senha)
    except CredenciaisInvalidas:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    gravar_cookie(request, resposta, token)
    return LoginSaida(token=token, tipo="bearer")


@roteador.post(
    "/sair",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(exigir_origem_com_cookie)],
    responses=erros(403),
)
async def sair(request: Request) -> Response:
    resposta = Response(status_code=status.HTTP_204_NO_CONTENT)
    # Formulário de outro site chega sem o cookie (SameSite) e não pode encerrar a sessão.
    if cookies_de_sessao(request):
        apagar_cookie(request, resposta)
    return resposta

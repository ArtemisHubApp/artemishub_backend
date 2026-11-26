from fastapi import APIRouter, Request, Response, status

from artemis_backend.adapters.autenticacao import Contas, Usuaria, token_invalido
from artemis_backend.adapters.esquemas_auth import ConsentimentoSaida, ContaSaida, PedidoNome
from artemis_backend.adapters.esquemas_de_erro import erros
from artemis_backend.adapters.sessao import apagar_cookie
from artemis_backend.domain.usuaria import CONSENTIMENTO, TokenInvalido

roteador = APIRouter(tags=["conta"])


@roteador.get("/v1/consentimento")
async def consentimento() -> ConsentimentoSaida:
    """Pública: a pessoa lê o texto antes de se cadastrar."""
    return ConsentimentoSaida(texto=CONSENTIMENTO)


@roteador.get("/v1/conta", responses=erros(401, 503))
async def ver(usuaria_id: Usuaria, contas: Contas) -> ContaSaida:
    try:
        usuaria = await contas.obter(usuaria_id)
    except TokenInvalido:
        raise token_invalido() from None
    return ContaSaida.de(usuaria)


@roteador.patch("/v1/conta", responses=erros(401, 403, 422, 503))
async def renomear(pedido: PedidoNome, usuaria_id: Usuaria, contas: Contas) -> ContaSaida:
    """Troca o nome da dona do token; id e e-mail não mudam por aqui."""
    try:
        return ContaSaida.de(await contas.renomear(usuaria_id, pedido.nome))
    except TokenInvalido:
        raise token_invalido() from None


@roteador.delete(
    "/v1/conta", status_code=status.HTTP_204_NO_CONTENT, responses=erros(401, 403, 503)
)
async def excluir(usuaria_id: Usuaria, contas: Contas, request: Request) -> Response:
    """Apaga a conta do token e, em cascata, as conversas e mensagens dela."""
    try:
        await contas.excluir(usuaria_id)
    except TokenInvalido:
        raise token_invalido() from None
    resposta = Response(status_code=status.HTTP_204_NO_CONTENT)
    apagar_cookie(request, resposta)
    return resposta

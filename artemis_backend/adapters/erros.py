import logging

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_log = logging.getLogger(__name__)

_INDISPONIVEL = {"detail": "Serviço indisponível, tente de novo"}
_INTERNO = {"detail": "Erro interno"}


def _falha_de_conexao(erro: BaseException) -> bool:
    """Só falhas de conexão com o banco: recusada ao conectar ou conexão do pool quebrada."""
    visto: set[int] = set()
    while erro is not None and id(erro) not in visto:
        visto.add(id(erro))
        if isinstance(erro, OSError | InterfaceError | OperationalError):
            return True
        if isinstance(erro, DBAPIError) and erro.connection_invalidated:
            return True
        erro = erro.__cause__ or erro.__context__
    return False


class ProtegeErros:
    """Responde 503 ou 500 em JSON sem deixar a exceção chegar ao servidor.

    A mensagem e o traceback podem citar e-mail ou senha, então o log leva só o tipo da
    exceção, o método e o modelo da rota.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        comecou = False

        async def enviar(mensagem: Message) -> None:
            nonlocal comecou
            comecou = comecou or mensagem["type"] == "http.response.start"
            await send(mensagem)

        try:
            await self._app(scope, receive, enviar)
        except Exception as erro:
            indisponivel = _falha_de_conexao(erro)
            rota = getattr(scope.get("route"), "path", "?")
            _log.error(
                "%s: %s em %s %s",
                "Banco indisponível" if indisponivel else "Erro inesperado",
                type(erro).__name__,
                scope["method"],
                rota,
            )
            if comecou:
                return
            resposta = JSONResponse(
                _INDISPONIVEL if indisponivel else _INTERNO, 503 if indisponivel else 500
            )
            await resposta(scope, receive, send)

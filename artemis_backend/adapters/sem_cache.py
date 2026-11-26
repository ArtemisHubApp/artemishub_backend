from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_PREFIXO = "/v1/"


class SemCache:
    """`Cache-Control: no-store` em tudo da API, inclusive nos erros dos outros middlewares."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(_PREFIXO):
            await self._app(scope, receive, send)
            return

        async def enviar(mensagem: Message) -> None:
            if mensagem["type"] == "http.response.start":
                MutableHeaders(scope=mensagem)["Cache-Control"] = "no-store"
            await send(mensagem)

        await self._app(scope, receive, enviar)

"""Respostas 422 no formato documentado, sem repetir o que foi enviado."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException

# O FastAPI responde 400 quando não consegue ler o corpo (não é UTF-8, número enorme, aninhado
# demais); as rotas da API nunca usam 400.
_CORPO_ILEGIVEL = 400
_DETALHE_DO_CORPO = {"loc": ["body"], "msg": "Corpo não é um JSON válido", "type": "json_invalid"}


async def _validacao_sem_eco(_: Request, erro: RequestValidationError) -> JSONResponse:
    """422 sem `input` nem `ctx`: o padrão do FastAPI devolveria a senha e o e-mail enviados."""
    detalhes = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in erro.errors()]
    return JSONResponse({"detail": detalhes}, 422)


async def _corpo_ilegivel_e_422(request: Request, erro: HTTPException) -> Response:
    if erro.status_code == _CORPO_ILEGIVEL:
        return JSONResponse({"detail": [_DETALHE_DO_CORPO]}, 422)
    return await http_exception_handler(request, erro)


def responder_422_sem_eco(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validacao_sem_eco)
    app.add_exception_handler(HTTPException, _corpo_ilegivel_e_422)

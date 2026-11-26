"""Cookie de sessão: leitura, gravação e remoção, sempre com os mesmos atributos."""

from fastapi import Request, Response

from artemis_backend.adapters.seguranca import DURACAO_DO_TOKEN
from artemis_backend.config import Config

NOME_DO_COOKIE = "artemis_sessao"


def cookies_de_sessao(request: Request) -> list[str]:
    """Todos os valores enviados: `request.cookies` guardaria um só, escondendo repetidos."""
    valores = []
    for cabecalho in request.headers.getlist("cookie"):
        for par in cabecalho.split(";"):
            nome, separador, valor = par.partition("=")
            # Só espaço e tab, como o navegador: strip() aceitaria `\xa0artemis_sessao`.
            if separador and nome.strip(" \t") == NOME_DO_COOKIE:
                valores.append(valor.strip(" \t"))
    return valores


def gravar_cookie(request: Request, resposta: Response, token: str) -> None:
    _definir(request, resposta, token, int(DURACAO_DO_TOKEN.total_seconds()))


def apagar_cookie(request: Request, resposta: Response) -> None:
    _definir(request, resposta, "", 0)


def _definir(request: Request, resposta: Response, valor: str, duracao: int) -> None:
    config: Config = request.app.state.config
    resposta.set_cookie(
        NOME_DO_COOKIE,
        valor,
        max_age=duracao,
        path="/",
        secure=config.cookie_seguro,
        httponly=True,
        samesite="strict",
    )

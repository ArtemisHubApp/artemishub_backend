"""Proteção contra pedidos feitos por outros sites (CSRF): confere o cabeçalho `Origin`."""

from fastapi import HTTPException, Request, status

from artemis_backend.adapters.sessao import cookies_de_sessao

_METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def _conferir(request: Request) -> None:
    if request.headers.getlist("origin") != [request.app.state.config.origem]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origem não permitida")


async def exigir_origem_com_cookie(request: Request) -> None:
    """O navegador anexa o cookie sozinho, então escrever com ele exige a origem do site."""
    if request.method not in _METODOS_SEGUROS and cookies_de_sessao(request):
        _conferir(request)


async def exigir_origem_sem_authorization(request: Request) -> None:
    """Com `Authorization` o cookie é ignorado, e a origem não importa."""
    if "authorization" not in request.headers:
        await exigir_origem_com_cookie(request)


async def recusar_outra_origem(request: Request) -> None:
    """Para rotas públicas: cliente que não é navegador não manda `Origin`."""
    if "origin" in request.headers:
        _conferir(request)

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import httpx
import jwt

from tests.apoio.valores import (
    ANA,
    NOME_DE_TESTE,
    ORIGEM_DE_TESTE,
    SEGREDO_DE_TESTE,
    SENHA_DE_TESTE,
)

COOKIE = "artemis_sessao"
ORIGEM_NEGADA = {"detail": "Origem não permitida"}
ATRIBUTOS = {"path": "/", "secure": True, "httponly": True, "samesite": "strict"}
APAGADO = {**ATRIBUTOS, "valor": "", "max-age": "0"}
ROTAS_PUBLICAS = {
    ("GET", "/health"),
    ("POST", "/v1/auth/cadastro"),
    ("POST", "/v1/auth/login"),
    ("POST", "/v1/auth/sair"),
    ("GET", "/v1/consentimento"),
}


def com_origem(cabecalhos: dict, origem: str | None) -> dict:
    sem_origem = {k: v for k, v in cabecalhos.items() if k != "Origin"}
    return sem_origem if origem is None else {**sem_origem, "Origin": origem}


async def logar(cliente, **cabecalhos) -> httpx.Response:
    corpo = {"email": ANA, "senha": SENHA_DE_TESTE}
    return await cliente.post("/v1/auth/login", json=corpo, headers=cabecalhos)


async def cadastrar(cliente, **cabecalhos) -> httpx.Response:
    corpo = {
        "nome": NOME_DE_TESTE,
        "email": ANA,
        "senha": SENHA_DE_TESTE,
        "consentimento": True,
    }
    return await cliente.post("/v1/auth/cadastro", json=corpo, headers=cabecalhos)


def atributos_do_cookie(resposta) -> dict:
    [bruto] = resposta.headers.get_list("set-cookie")
    [(nome, cookie)] = SimpleCookie(bruto).items()
    assert nome == COOKIE
    return {
        "valor": cookie.value,
        **{k: v.lower() if isinstance(v, str) else v for k, v in cookie.items() if v},
    }


def token(sub: str | None = None, *, exp: datetime | None = None, segredo=SEGREDO_DE_TESTE, **kw):
    agora = datetime.now(UTC)
    carga = {"sub": sub, "exp": exp or agora + timedelta(minutes=5), "iat": agora}
    carga = {k: v for k, v in carga.items() if v is not None}
    return jwt.encode(carga, segredo, algorithm="HS256", **kw)


def rotas_protegidas(app) -> list[tuple[str, str]]:
    # O OpenAPI lista todas as rotas já com o prefixo, o que app.routes não faz mais.
    achadas = {
        (metodo.upper(), caminho)
        for caminho, operacoes in app.openapi()["paths"].items()
        for metodo in operacoes
    }
    return sorted(achadas - ROTAS_PUBLICAS)


def em_cookie(autorizacao: dict) -> dict:
    token = autorizacao["Authorization"].removeprefix("Bearer ")
    return {"Cookie": f"artemis_sessao={token}", "Origin": ORIGEM_DE_TESTE}

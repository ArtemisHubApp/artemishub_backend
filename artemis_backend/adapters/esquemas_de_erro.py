"""Corpos de erro da API e onde cada um acontece, para o OpenAPI."""

from typing import Any

from pydantic import BaseModel


class Erro(BaseModel):
    detail: str


class DetalheDeValidacao(BaseModel):
    """Sem o valor enviado: o 422 não repete senha, e-mail nem pergunta."""

    loc: list[str | int]
    msg: str
    type: str


class ErroDeValidacao(BaseModel):
    detail: list[DetalheDeValidacao]


_DESCRICOES = {
    401: "Sem sessão válida",
    403: "Origem não permitida",
    404: "Conversa não encontrada",
    409: "Conflito com o que já existe",
    422: "Pedido inválido",
    503: "Banco indisponível",
}

Respostas = dict[int | str, dict[str, Any]]


def erros(*status: int) -> Respostas:
    """Documentação das respostas de erro de uma rota."""
    return {
        s: {"model": ErroDeValidacao if s == 422 else Erro, "description": _DESCRICOES[s]}
        for s in status
    }

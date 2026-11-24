import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError

from artemis_backend.adapters.autenticacao import Usuaria, token_invalido
from artemis_backend.adapters.conversa_inexistente import nao_encontrada
from artemis_backend.adapters.cursor import (
    CURSOR_MAXIMO,
    CursorInvalido,
    escrever_cursor,
    ler_cursor,
)
from artemis_backend.adapters.esquemas_conversas import (
    ConversaDetalheSaida,
    ConversaSaida,
    PaginaDeConversasSaida,
)
from artemis_backend.application.conversas import ServicoConversas
from artemis_backend.domain.conversa import (
    PAGINA_MAXIMA,
    PAGINA_PADRAO,
    ConversaInexistente,
    PosicaoNaLista,
    UsuariaInexistente,
)

roteador = APIRouter(prefix="/v1/conversas", tags=["conversas"])


def _servico(request: Request) -> ServicoConversas:
    return request.app.state.conversas


Servico = Annotated[ServicoConversas, Depends(_servico)]


def _posicao_do_cursor(
    cursor: Annotated[str | None, Query(max_length=CURSOR_MAXIMO)] = None,
) -> PosicaoNaLista | None:
    if cursor is None:
        return None
    try:
        return ler_cursor(cursor)
    except CursorInvalido:
        erro = {"loc": ("query", "cursor"), "msg": "Cursor inválido", "type": "cursor_invalido"}
        raise RequestValidationError([erro]) from None


@roteador.get("", response_model=PaginaDeConversasSaida)
async def listar(
    usuaria_id: Usuaria,
    servico: Servico,
    depois_de: Annotated[PosicaoNaLista | None, Depends(_posicao_do_cursor)],
    limite: Annotated[int, Query(ge=1, le=PAGINA_MAXIMA)] = PAGINA_PADRAO,
):
    pagina = await servico.listar(usuaria_id, limite, depois_de)
    proximo = None if pagina.proxima is None else escrever_cursor(pagina.proxima)
    return {"itens": pagina.itens, "proximo": proximo}


@roteador.post("", status_code=status.HTTP_201_CREATED, response_model=ConversaSaida)
async def criar(usuaria_id: Usuaria, servico: Servico):
    try:
        return await servico.criar(usuaria_id)
    except UsuariaInexistente:
        # Conta apagada entre a checagem do token e a gravação: igual a um token inválido.
        raise token_invalido() from None


@roteador.get("/{conversa_id}", response_model=ConversaDetalheSaida)
async def detalhar(conversa_id: uuid.UUID, usuaria_id: Usuaria, servico: Servico):
    try:
        historico = await servico.obter(usuaria_id, conversa_id)
    except ConversaInexistente:
        raise nao_encontrada() from None
    return {**dataclasses.asdict(historico.conversa), "mensagens": historico.mensagens}


@roteador.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_todas(usuaria_id: Usuaria, servico: Servico) -> Response:
    await servico.apagar_todas(usuaria_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roteador.delete("/{conversa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar(conversa_id: uuid.UUID, usuaria_id: Usuaria, servico: Servico) -> Response:
    try:
        await servico.apagar(usuaria_id, conversa_id)
    except ConversaInexistente:
        raise nao_encontrada() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)

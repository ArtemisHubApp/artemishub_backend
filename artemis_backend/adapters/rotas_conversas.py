import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from artemis_backend.adapters.autenticacao import Usuaria, token_invalido
from artemis_backend.adapters.conversa_inexistente import nao_encontrada
from artemis_backend.adapters.esquemas_conversas import ConversaDetalheSaida, ConversaSaida
from artemis_backend.application.conversas import ServicoConversas
from artemis_backend.domain.conversa import ConversaInexistente, UsuariaInexistente

roteador = APIRouter(prefix="/v1/conversas", tags=["conversas"])


def _servico(request: Request) -> ServicoConversas:
    return request.app.state.conversas


Servico = Annotated[ServicoConversas, Depends(_servico)]


@roteador.get("", response_model=list[ConversaSaida])
async def listar(usuaria_id: Usuaria, servico: Servico):
    return await servico.listar(usuaria_id)


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

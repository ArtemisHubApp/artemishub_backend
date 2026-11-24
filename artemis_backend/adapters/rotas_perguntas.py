import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from artemis_backend.adapters.autenticacao import Usuaria
from artemis_backend.adapters.conversa_inexistente import nao_encontrada
from artemis_backend.adapters.esquemas_conversas import PedidoPergunta, PerguntaRespondidaSaida
from artemis_backend.application.perguntar import ServicoPerguntas
from artemis_backend.domain.conversa import ConversaInexistente, ConversaOcupada

roteador = APIRouter(prefix="/v1/conversas", tags=["conversas"])


def _perguntas(request: Request) -> ServicoPerguntas:
    return request.app.state.perguntas


Perguntas = Annotated[ServicoPerguntas, Depends(_perguntas)]


@roteador.post(
    "/{conversa_id}/mensagens",
    status_code=status.HTTP_201_CREATED,
    response_model=PerguntaRespondidaSaida,
)
async def perguntar(
    conversa_id: uuid.UUID, pedido: PedidoPergunta, usuaria_id: Usuaria, servico: Perguntas
):
    try:
        pergunta, resposta = await servico.perguntar(usuaria_id, conversa_id, pedido.pergunta)
    except ConversaInexistente:
        raise nao_encontrada() from None
    except ConversaOcupada:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já há uma pergunta em andamento nesta conversa"
        ) from None
    return {"pergunta": pergunta, "resposta": resposta}

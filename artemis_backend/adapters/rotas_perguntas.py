import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from artemis_backend.adapters.autenticacao import Usuaria
from artemis_backend.adapters.conversa_inexistente import nao_encontrada
from artemis_backend.adapters.esquemas_conversas import (
    ErroDeConflito,
    Motivo,
    PedidoPergunta,
    PerguntaRespondidaSaida,
)
from artemis_backend.adapters.esquemas_de_erro import erros
from artemis_backend.application.perguntar import ServicoPerguntas
from artemis_backend.domain.conversa import ConversaInexistente, ConversaOcupada, RespostaExpirada

roteador = APIRouter(prefix="/v1/conversas", tags=["conversas"])


def _perguntas(request: Request) -> ServicoPerguntas:
    return request.app.state.perguntas


def _conflito(codigo: Motivo, detail: str) -> JSONResponse:
    erro = ErroDeConflito(detail=detail, codigo=codigo)
    return JSONResponse(erro.model_dump(), status.HTTP_409_CONFLICT)


Perguntas = Annotated[ServicoPerguntas, Depends(_perguntas)]


@roteador.post(
    "/{conversa_id}/mensagens",
    status_code=status.HTTP_201_CREATED,
    response_model=PerguntaRespondidaSaida,
    responses={
        **erros(401, 403, 404, 422, 503),
        409: {"model": ErroDeConflito, "description": "Conversa ocupada ou resposta expirada"},
    },
)
async def perguntar(
    conversa_id: uuid.UUID, pedido: PedidoPergunta, usuaria_id: Usuaria, servico: Perguntas
):
    try:
        pergunta, resposta = await servico.perguntar(usuaria_id, conversa_id, pedido.pergunta)
    except ConversaInexistente:
        raise nao_encontrada() from None
    except ConversaOcupada:
        return _conflito("ocupada", "Já há uma pergunta em andamento nesta conversa")
    except RespostaExpirada:
        return _conflito(
            "expirada", "A resposta demorou demais e foi descartada; a pergunta está no histórico"
        )
    return {"pergunta": pergunta, "resposta": resposta}

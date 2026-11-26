"""Leitura das tabelas de conversas: colunas, ordem e conversão para o domínio."""

from sqlalchemy import case

from artemis_backend.adapters.tabelas import Conversa as LinhaConversa
from artemis_backend.adapters.tabelas import Mensagem as LinhaMensagem
from artemis_backend.domain.conversa import PAPEL_USUARIA, Conversa, Mensagem

COLUNAS_DA_CONVERSA = (
    LinhaConversa.id,
    LinhaConversa.titulo,
    LinhaConversa.criada_em,
    LinhaConversa.atualizada_em,
)

ORDEM_DAS_MENSAGENS = (
    LinhaMensagem.criada_em,
    case((LinhaMensagem.papel == PAPEL_USUARIA, 0), else_=1),
    LinhaMensagem.id,
)


def para_conversa(linha) -> Conversa:
    return Conversa(
        id=linha.id,
        titulo=linha.titulo,
        criada_em=linha.criada_em,
        atualizada_em=linha.atualizada_em,
    )


def para_mensagem(linha: LinhaMensagem) -> Mensagem:
    return Mensagem(
        id=linha.id,
        papel=linha.papel,
        texto=linha.texto,
        criada_em=linha.criada_em,
        aprovada=linha.aprovada,
        bloqueada=linha.bloqueada,
        trace_id=linha.trace_id,
        pergunta_id=linha.pergunta_id,
    )

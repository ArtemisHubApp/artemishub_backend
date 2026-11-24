import uuid
from dataclasses import dataclass
from datetime import datetime

PAPEL_USUARIA = "usuaria"
PAPEL_ARTEMIS = "artemis"
TITULO_MAXIMO = 60
TROCAS_NA_MEMORIA = 3


class ConversaInexistente(Exception):
    """Não existe conversa com esse id para essa usuária (inclui a que é de outra)."""


@dataclass(frozen=True)
class Troca:
    pergunta: str
    resposta: str


@dataclass(frozen=True)
class Mensagem:
    id: uuid.UUID
    papel: str
    texto: str
    criada_em: datetime
    aprovada: bool
    bloqueada: bool
    trace_id: str | None
    pergunta_id: uuid.UUID | None


@dataclass(frozen=True)
class Conversa:
    id: uuid.UUID
    titulo: str | None
    criada_em: datetime
    atualizada_em: datetime


@dataclass(frozen=True)
class ConversaComMensagens:
    conversa: Conversa
    mensagens: tuple[Mensagem, ...]


def titulo_da_conversa(pergunta: str) -> str:
    """Começo da pergunta com até 60 caracteres, sem partir palavra e sem quebras de linha."""
    texto = " ".join(pergunta.split())
    if len(texto) <= TITULO_MAXIMO:
        return texto
    corte = texto[:TITULO_MAXIMO]
    if texto[TITULO_MAXIMO] != " " and " " in corte:
        corte = corte.rsplit(" ", 1)[0]
    return corte.rstrip()


def memoria_curta(mensagens: list[Mensagem]) -> list[Troca]:
    """Últimas 3 trocas da conversa que a Artemis respondeu e o guardrail aprovou.

    Cada resposta é ligada à pergunta por `pergunta_id`, e a entrada pode vir em qualquer
    ordem. O texto segue como foi exibido: a limpeza (fontes, citações, corte) é do agents.
    """
    ordenadas = sorted(mensagens, key=lambda m: m.criada_em)
    respostas: dict[uuid.UUID, Mensagem] = {}
    for m in ordenadas:
        if m.papel == PAPEL_ARTEMIS and m.aprovada and not m.bloqueada and m.pergunta_id:
            respostas.setdefault(m.pergunta_id, m)
    trocas = [
        Troca(pergunta=m.texto, resposta=respostas[m.id].texto)
        for m in ordenadas
        if m.papel == PAPEL_USUARIA and m.id in respostas
    ]
    return trocas[-TROCAS_NA_MEMORIA:]

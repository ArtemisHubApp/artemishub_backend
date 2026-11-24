"""Respostas marcadas como simuladas. Um trecho na pergunta escolhe o modo."""

from typing import Any

LENTO = "#lento"
ERRO = "#erro"
_BLOQUEADA = "#bloqueada"
_ESCOPO = "#escopo"

_TEXTO = (
    "[SIMULADO] Esta é uma resposta de teste, sem dados reais. Ela só mostra como a conversa "
    "aparece na tela [FONTE 1].\n\n"
    "Fontes:\n"
    "[FONTE 1] Fonte fictícia, só para teste: https://example.com/fonte-ficticia"
)
_TEXTO_BLOQUEADA = "[SIMULADO] Esta resposta de teste foi bloqueada."
_TEXTO_ESCOPO = "[SIMULADO] Esta pergunta de teste está fora do escopo da Artemis."


def responder(pergunta: str) -> dict[str, Any]:
    bloqueada = _BLOQUEADA in pergunta
    fora_de_escopo = _ESCOPO in pergunta
    if bloqueada:
        texto = _TEXTO_BLOQUEADA
    elif fora_de_escopo:
        texto = _TEXTO_ESCOPO
    else:
        texto = _TEXTO
    return {
        "resposta": texto,
        "aprovada": not (bloqueada or fora_de_escopo),
        "bloqueada": bloqueada,
        "fora_de_escopo": fora_de_escopo,
        "lembranca": None,
        "trace_id": "simulado",
        "passos": ["simulado"],
    }

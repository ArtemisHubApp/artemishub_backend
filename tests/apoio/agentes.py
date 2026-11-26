import asyncio

from artemis_backend.application.perguntar import RespostaAgentes


def resposta_dos_agentes(**campos) -> RespostaAgentes:
    padrao = {
        "resposta": "Resposta da Artemis",
        "aprovada": True,
        "bloqueada": False,
        "fora_de_escopo": False,
        "lembranca": None,
        "trace_id": "trace",
    }
    return RespostaAgentes(**{**padrao, **campos})


class AgentesFake:
    """Guarda cada pedido. Depois de bloquear(), só responde (ou falha) após liberar()."""

    def __init__(self) -> None:
        self.chamadas: list[tuple] = []
        self.resposta = resposta_dos_agentes()
        self.erro: Exception | None = None
        self.chamado = asyncio.Event()
        self._livre = asyncio.Event()
        self._livre.set()

    def bloquear(self) -> None:
        self._livre.clear()

    def liberar(self) -> None:
        self._livre.set()

    async def responder(self, pergunta, sessao, historico, lembranca) -> RespostaAgentes:
        self.chamadas.append((pergunta, sessao, historico, lembranca))
        self.chamado.set()
        await self._livre.wait()
        if self.erro:
            raise self.erro
        return self.resposta

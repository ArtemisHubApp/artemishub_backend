import asyncio
import logging
from typing import Annotated, Any

import httpx
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from artemis_backend.application.portas import AgentesIndisponiveis, RespostaAgentes
from artemis_backend.domain.conversa import Troca

_log = logging.getLogger(__name__)

_LIMITE_EM_SEGUNDOS = 60.0


def _sem_nul(texto: str) -> str:
    # O Postgres não guarda NUL; surrogate solto o leitor de JSON do pydantic já recusa.
    if "\x00" in texto:
        raise ValueError("caractere inválido")
    return texto


def _com_conteudo(texto: str) -> str:
    if not texto.strip():
        raise ValueError("texto vazio")
    return texto


Texto = Annotated[str, AfterValidator(_sem_nul)]
Curto = Annotated[Texto, Field(max_length=200)]


class _Contrato(BaseModel):
    """Espelha contratos/responder.v1.schema.json, sem conversão de tipos nem campo a mais."""

    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


class _Lembranca(_Contrato):
    salario: bool
    direitos: bool
    cbo_familia: Annotated[Texto, Field(max_length=20)] | None
    cbo_familia_nome: Curto | None
    ocupacao: Curto | None
    uf: Annotated[Texto, Field(max_length=2)] | None


class _Resposta(_Contrato):
    resposta: Annotated[Texto, Field(max_length=20_000), AfterValidator(_com_conteudo)]
    aprovada: bool
    bloqueada: bool
    fora_de_escopo: bool
    lembranca: _Lembranca | None
    trace_id: Curto
    passos: list[Texto]


class AgentesHttp:
    """Cliente do `POST /v1/responder`. Não registra corpo nem token; não tenta de novo."""

    def __init__(
        self,
        url: str,
        token: str,
        timeout: float = _LIMITE_EM_SEGUNDOS,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endereco = url.rstrip("/") + "/v1/responder"
        self._timeout = timeout
        # O limite do httpx é por operação (cada leitura zera a conta); o que vale é o total,
        # em _enviar.
        self._cliente = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=None,
            follow_redirects=False,
            trust_env=False,
            transport=transporte,
        )

    async def responder(
        self,
        pergunta: str,
        sessao: str,
        historico: list[Troca],
        lembranca: dict[str, Any] | None,
    ) -> RespostaAgentes:
        pedido = {
            "pergunta": pergunta,
            "sessao": sessao,
            "historico": [{"pergunta": t.pergunta, "resposta": t.resposta} for t in historico],
            "lembranca": lembranca,
        }
        resposta = await self._enviar(pedido)
        if resposta.status_code != httpx.codes.OK:
            raise self._indisponiveis(f"status {resposta.status_code}")
        try:
            lida = _Resposta.model_validate_json(resposta.content)
        except ValidationError:
            # A mensagem do pydantic pode citar o conteúdo recebido.
            raise self._indisponiveis("resposta fora do contrato") from None
        return RespostaAgentes(**lida.model_dump(exclude={"passos"}))

    async def fechar(self) -> None:
        await self._cliente.aclose()

    async def _enviar(self, pedido: dict[str, Any]) -> httpx.Response:
        try:
            async with asyncio.timeout(self._timeout):
                return await self._cliente.post(self._endereco, json=pedido)
        except (httpx.HTTPError, httpx.InvalidURL, OSError) as erro:  # TimeoutError é OSError
            raise self._indisponiveis(type(erro).__name__) from None

    @staticmethod
    def _indisponiveis(motivo: str) -> AgentesIndisponiveis:
        _log.warning("Agentes indisponíveis: %s", motivo)
        return AgentesIndisponiveis(motivo)

"""Servidor HTTP do simulador: só 127.0.0.1, com token de serviço e sem registrar pedidos."""

import hmac
import json
import os
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer, ThreadingMixIn
from typing import Any

from ferramentas.agentes_simulados.pedido import pedido_valido
from ferramentas.agentes_simulados.resposta import ERRO, LENTO, responder

HOST = "127.0.0.1"
_HOSTS_ACEITOS = {HOST, "localhost"}
_ROTA = "/v1/responder"
_ESPERA_LENTA = 5.0
# Cabem a pergunta e três trocas do tamanho máximo, com folga.
_CORPO_MAXIMO = 512 * 1024


class _Recusa(Exception):
    def __init__(self, status: int, motivo: str) -> None:
        self.status = status
        self.motivo = motivo


class Servidor(ThreadingMixIn, TCPServer):
    daemon_threads = True
    # No Windows, SO_REUSEADDR deixaria dois processos na mesma porta.
    allow_reuse_address = os.name == "posix"

    def __init__(self, porta: int, token: str, esperar: Callable[[float], None]) -> None:
        self.autorizacao = f"Bearer {token}".encode()
        self.esperar = esperar
        super().__init__((HOST, porta), _Atendente)

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Conexão que caiu no meio: o traceback padrão poderia citar o pedido."""


def criar_servidor(
    porta: int, token: str, esperar: Callable[[float], None] = time.sleep
) -> Servidor:
    return Servidor(porta, token, esperar)


class _Atendente(BaseHTTPRequestHandler):
    server: Servidor
    timeout = 10

    def do_POST(self) -> None:
        try:
            corpo = self._ler_corpo()
            self._conferir_acesso()
            pergunta = self._ler_pergunta(corpo)
            if LENTO in pergunta:
                self.server.esperar(_ESPERA_LENTA)
            if ERRO in pergunta:
                raise _Recusa(500, "Erro simulado")
        except _Recusa as recusa:
            self._enviar(recusa.status, {"detail": recusa.motivo})
        else:
            self._enviar(200, responder(pergunta))

    def log_message(self, format: str, *args: Any) -> None:
        """Nada do pedido vai para o terminal."""

    def _ler_corpo(self) -> bytes:
        # Lido antes de recusar: fechar com bytes pendentes derruba a conexão sem resposta.
        tamanhos = self.headers.get_all("Content-Length", [])
        if "Transfer-Encoding" in self.headers or len(tamanhos) != 1:
            raise _Recusa(411, "Informe um Content-Length")
        tamanho = tamanhos[0].strip()
        if not (tamanho.isascii() and tamanho.isdigit()):
            raise _Recusa(411, "Content-Length inválido")
        if len(tamanho) > len(str(_CORPO_MAXIMO)) or int(tamanho) > _CORPO_MAXIMO:
            raise _Recusa(413, "Pedido grande demais")
        return self.rfile.read(int(tamanho))

    def _conferir_acesso(self) -> None:
        host = self.headers.get("Host", "").partition(":")[0]
        if host not in _HOSTS_ACEITOS:
            raise _Recusa(403, "Só atende este computador")
        if self.path != _ROTA:
            raise _Recusa(404, "Rota inexistente")
        autorizacoes = self.headers.get_all("Authorization", [])
        if len(autorizacoes) != 1 or not hmac.compare_digest(
            autorizacoes[0].encode(), self.server.autorizacao
        ):
            raise _Recusa(401, "Token de serviço inválido")

    def _ler_pergunta(self, corpo: bytes) -> str:
        try:
            pedido = json.loads(corpo)
        except (ValueError, RecursionError):
            pedido = None
        if not pedido_valido(pedido):
            raise _Recusa(422, "Pedido fora do contrato")
        return pedido["pergunta"]

    def _enviar(self, status: int, conteudo: dict[str, Any]) -> None:
        corpo = json.dumps(conteudo, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from ferramentas.agentes_simulados.servidor import criar_servidor

TOKEN = "token-de-servico-de-teste"
AUTORIZADA = {"Authorization": f"Bearer {TOKEN}"}


@contextmanager
def simulador_no_ar(esperar: Callable[[float], None] = time.sleep) -> Iterator[str]:
    """Sobe o simulador numa porta livre e devolve a base da URL."""
    servidor = criar_servidor(0, TOKEN, esperar)
    tarefa = threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.01})
    tarefa.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}"
    finally:
        servidor.shutdown()
        tarefa.join()
        servidor.server_close()


def pedido(pergunta: str = "Quanto ganha uma dev?", **campos) -> dict:
    return {"pergunta": pergunta, "sessao": "s1", "historico": [], "lembranca": None, **campos}

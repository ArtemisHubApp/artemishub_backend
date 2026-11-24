import argparse
import os

from ferramentas.agentes_simulados.servidor import HOST, criar_servidor

_VARIAVEL = "ARTEMIS_AGENTS_TOKEN"
_PORTA_PADRAO = 8001


def _porta(valor: str) -> int:
    porta = int(valor)
    if not 0 <= porta <= 65535:
        raise ValueError
    return porta


def main() -> None:
    leitor = argparse.ArgumentParser(
        prog="python -m ferramentas.agentes_simulados",
        description="Agentes simulados, só para desenvolvimento e só neste computador.",
    )
    leitor.add_argument("--porta", type=_porta, default=_PORTA_PADRAO, help="0 escolhe uma livre")
    porta = leitor.parse_args().porta
    token = os.environ.get(_VARIAVEL, "").strip()
    if not token:
        leitor.error(f"defina {_VARIAVEL} com o mesmo token usado pelo backend")
    with criar_servidor(porta, token) as servidor:
        print(f"Agentes simulados em http://{HOST}:{servidor.server_address[1]}", flush=True)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            print("Agentes simulados encerrados")


if __name__ == "__main__":
    main()

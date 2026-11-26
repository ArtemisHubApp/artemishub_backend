"""Grava contratos/openapi.json, de onde o frontend gera os tipos."""

import json
from pathlib import Path

from artemis_backend.config import Config
from artemis_backend.main import criar_app

ARQUIVO = Path(__file__).resolve().parent.parent / "contratos" / "openapi.json"
# O documento não depende da configuração; nada aqui é usado nem precisa existir.
_CONFIG = Config(
    database_url="postgresql+asyncpg://localhost/exportacao",
    jwt_segredo="exportacao-do-openapi-sem-segredo",
    agents_url="http://localhost",
    agents_token="exportacao",
    origem="http://localhost",
)


def documento() -> str:
    """O mesmo texto a cada execução: chaves ordenadas e quebra de linha no fim."""
    openapi = criar_app(_CONFIG).openapi()
    return json.dumps(openapi, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    ARQUIVO.write_text(documento(), "utf-8", newline="\n")


if __name__ == "__main__":
    main()

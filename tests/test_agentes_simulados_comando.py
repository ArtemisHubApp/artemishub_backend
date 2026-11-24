import ast
import os
import socket
import subprocess
import sys
import tomllib

import httpx
import pytest

from ferramentas.agentes_simulados.servidor import criar_servidor
from tests.apoio.simulador import AUTORIZADA, TOKEN, pedido
from tests.apoio.valores import RAIZ

COMANDO = [sys.executable, "-u", "-m", "ferramentas.agentes_simulados"]


def ambiente(token: str | None) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items() if k != "ARTEMIS_AGENTS_TOKEN"}
    return base if token is None else {**base, "ARTEMIS_AGENTS_TOKEN": token}


def rodar(*argumentos: str, token: str | None = TOKEN) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*COMANDO, *argumentos],
        cwd=RAIZ,
        env=ambiente(token),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


@pytest.mark.parametrize("token", [None, "", "   "])
def test_sem_token_nao_sobe(token):
    r = rodar("--porta", "0", token=token)
    assert r.returncode == 2
    assert "ARTEMIS_AGENTS_TOKEN" in r.stderr


@pytest.mark.parametrize(
    "argumentos", [["--host", "0.0.0.0"], ["--porta", "x"], ["--porta", "70000"], ["--porta=-1"]]
)
def test_outro_host_ou_porta_invalida_nao_sobe(argumentos):
    r = rodar(*argumentos)
    assert r.returncode == 2
    assert TOKEN not in r.stdout + r.stderr


def test_comando_sobe_e_responde():
    processo = subprocess.Popen(
        [*COMANDO, "--porta", "0"],
        cwd=RAIZ,
        env=ambiente(TOKEN),
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        url = processo.stdout.readline().split()[-1]
        assert url.startswith("http://127.0.0.1:")
        r = httpx.post(url + "/v1/responder", json=pedido(), headers=AUTORIZADA, trust_env=False)
        assert r.status_code == 200
    finally:
        processo.kill()
        processo.communicate()


def test_so_escuta_em_127_0_0_1():
    servidor = criar_servidor(0, TOKEN)
    try:
        assert servidor.server_address[0] == "127.0.0.1"
        assert servidor.socket.family == socket.AF_INET
    finally:
        servidor.server_close()


def test_so_usa_a_biblioteca_padrao():
    arquivos = list((RAIZ / "ferramentas" / "agentes_simulados").glob("*.py"))
    assert arquivos
    for arquivo in arquivos:
        for no in ast.walk(ast.parse(arquivo.read_text("utf-8"))):
            modulos = []
            if isinstance(no, ast.Import):
                modulos = [nome.name for nome in no.names]
            elif isinstance(no, ast.ImportFrom):
                modulos = [no.module]
            for modulo in modulos:
                raiz = modulo.split(".")[0]
                assert raiz == "ferramentas" or raiz in sys.stdlib_module_names, modulo


def test_fica_fora_do_pacote_de_producao():
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text("utf-8"))
    assert projeto["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["artemis_backend"]
    for arquivo in (RAIZ / "artemis_backend").rglob("*.py"):
        assert "ferramentas" not in arquivo.read_text("utf-8"), arquivo

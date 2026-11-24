from artemis_backend.config import Config
from tests.conftest import RAIZ


def ler_env_example() -> dict[str, str]:
    valores = {}
    for linha in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        if linha.strip() and not linha.lstrip().startswith("#"):
            nome, _, valor = linha.partition("=")
            valores[nome.strip()] = valor.strip()
    return valores


def test_env_example_nao_traz_segredo_utilizavel():
    valores = ler_env_example()
    assert valores["ARTEMIS_JWT_SEGREDO"] == ""
    assert valores["ARTEMIS_AGENTS_TOKEN"] == ""


def test_env_example_sobe_so_com_os_segredos_preenchidos(monkeypatch):
    for nome, valor in ler_env_example().items():
        monkeypatch.setenv(nome, valor or "segredo-falso-so-para-testes-com-mais-de-32-bytes")
    config = Config.de_ambiente()
    assert (config.origem, config.cookie_seguro) == ("http://localhost:5173", False)

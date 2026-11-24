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

from dataclasses import replace

import pytest

from artemis_backend.config import Config

ORIGENS_LOCAIS = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
ORIGENS_HTTPS = [
    "https://artemis.example.com",
    "https://artemis.example.com:8443",
    "https://localhost:5173",
]


@pytest.fixture
def ambiente(monkeypatch):
    for nome, valor in {
        "DATABASE_URL": "x",
        "ARTEMIS_JWT_SEGREDO": "s" * 32,
        "ARTEMIS_AGENTS_URL": "x",
        "ARTEMIS_AGENTS_TOKEN": "x",
        "ARTEMIS_ORIGEM": "http://localhost:5173",
    }.items():
        monkeypatch.setenv(nome, valor)
    monkeypatch.delenv("ARTEMIS_COOKIE_SEGURO", raising=False)
    return monkeypatch


@pytest.mark.parametrize("origem", ORIGENS_LOCAIS + ORIGENS_HTTPS)
def test_origem_valida(ambiente, origem):
    ambiente.setenv("ARTEMIS_ORIGEM", origem)
    assert Config.de_ambiente().origem == origem


@pytest.mark.parametrize(
    "origem",
    [
        "x",
        "*",
        "null",
        "artemis.example.com",
        "//artemis.example.com",
        "ftp://artemis.example.com",
        "http://artemis.example.com",
        "http://localhost.example.com",
        "http://127.0.0.1.example.com",
        "https://artemis.example.com/",
        "https://artemis.example.com/app",
        "https://artemis.example.com?a=1",
        "https://artemis.example.com#a",
        "https://ana:senha@artemis.example.com",
        "https://artemis.example.com:",
        "https://artemis.example.com:0",
        "https://artemis.example.com:porta",
        "https://artemis.example.com:65536",
        # O navegador manda o host em minúsculas e omite a porta padrão: nunca seriam iguais.
        "https://Artemis.example.com",
        "https://artemis.example.com:443",
        "http://localhost:80",
        "https://artemis.example.com https://outro.example.com",
        "https://artemis.example.com\nhttps://outro.example.com",
        "https://ártemis.example.com",
    ],
)
def test_origem_invalida_nao_sobe(ambiente, origem):
    ambiente.setenv("ARTEMIS_ORIGEM", origem)
    with pytest.raises(ValueError, match="ARTEMIS_ORIGEM") as erro:
        Config.de_ambiente()
    assert "senha" not in str(erro.value)


def test_cookie_e_seguro_por_padrao(ambiente):
    assert Config.de_ambiente().cookie_seguro is True


@pytest.mark.parametrize("valor, esperado", [("true", True), ("false", False)])
def test_cookie_seguro_le_true_e_false(ambiente, valor, esperado):
    ambiente.setenv("ARTEMIS_COOKIE_SEGURO", valor)
    assert Config.de_ambiente().cookie_seguro is esperado


@pytest.mark.parametrize("valor", ["", "False", "TRUE", "0", "1", "no", " false"])
def test_cookie_seguro_recusa_outro_valor(ambiente, valor):
    ambiente.setenv("ARTEMIS_COOKIE_SEGURO", valor)
    with pytest.raises(ValueError, match="ARTEMIS_COOKIE_SEGURO"):
        Config.de_ambiente()


@pytest.mark.parametrize("origem", ORIGENS_LOCAIS)
def test_cookie_inseguro_em_localhost(config, origem):
    assert replace(config, origem=origem, cookie_seguro=False).cookie_seguro is False


@pytest.mark.parametrize("origem", ORIGENS_HTTPS)
def test_cookie_inseguro_so_em_localhost(config, origem):
    with pytest.raises(ValueError, match="ARTEMIS_COOKIE_SEGURO"):
        replace(config, origem=origem, cookie_seguro=False)

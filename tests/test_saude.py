import pytest

from artemis_backend.config import Config
from artemis_backend.main import app_de_ambiente


async def test_saude(cliente):
    r = await cliente.get("/health")
    assert (r.status_code, r.json()) == (200, {"status": "ok"})


def test_config_le_as_variaveis_do_ambiente(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
    monkeypatch.setenv("ARTEMIS_JWT_SEGREDO", "segredo")
    monkeypatch.setenv("ARTEMIS_AGENTS_URL", "http://agentes")
    monkeypatch.setenv("ARTEMIS_AGENTS_TOKEN", "token")
    config = Config.de_ambiente()
    assert (config.database_url, config.jwt_segredo) == ("postgresql+asyncpg://u:p@h/d", "segredo")
    assert (config.agents_url, config.agents_token) == ("http://agentes", "token")


def test_config_sem_segredo_nao_sobe(monkeypatch):
    monkeypatch.delenv("ARTEMIS_JWT_SEGREDO", raising=False)
    with pytest.raises(ValueError, match="ARTEMIS_JWT_SEGREDO"):
        Config.de_ambiente()


@pytest.mark.parametrize("valor", ["", "   "])
def test_segredo_vazio_conta_como_ausente(monkeypatch, valor):
    monkeypatch.setenv("ARTEMIS_JWT_SEGREDO", valor)
    with pytest.raises(ValueError, match="ARTEMIS_JWT_SEGREDO"):
        Config.de_ambiente()


@pytest.mark.parametrize("variavel", ["DATABASE_URL", "ARTEMIS_AGENTS_URL", "ARTEMIS_AGENTS_TOKEN"])
def test_variavel_ausente_e_nomeada_no_erro(monkeypatch, variavel):
    for nome, valor in [
        ("DATABASE_URL", "x"),
        ("ARTEMIS_JWT_SEGREDO", "x"),
        ("ARTEMIS_AGENTS_URL", "x"),
        ("ARTEMIS_AGENTS_TOKEN", "x"),
    ]:
        monkeypatch.setenv(nome, valor)
    monkeypatch.delenv(variavel)
    with pytest.raises(ValueError, match=variavel):
        Config.de_ambiente()


def test_segredos_nao_aparecem_no_repr():
    config = Config(
        database_url="postgresql+asyncpg://u:senha-do-banco@h/d",
        jwt_segredo="segredo-jwt",
        agents_url="http://agentes",
        agents_token="token-agentes",
    )
    texto = repr(config)
    assert not any(s in texto for s in ["senha-do-banco", "segredo-jwt", "token-agentes"])


def test_app_de_ambiente_nao_sobe_sem_segredo(monkeypatch):
    monkeypatch.delenv("ARTEMIS_JWT_SEGREDO", raising=False)
    with pytest.raises(ValueError, match="ARTEMIS_JWT_SEGREDO"):
        app_de_ambiente()

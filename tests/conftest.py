import asyncio
import uuid
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from artemis_backend.adapters.banco import criar_fabrica_de_sessoes
from artemis_backend.config import Config
from artemis_backend.main import criar_app

SEGREDO_DE_TESTE = "segredo-falso-so-para-testes-com-mais-de-32-bytes"
SENHA_DE_TESTE = "senha-de-teste-123"
RAIZ = Path(__file__).resolve().parent.parent


def config_alembic(url: str) -> AlembicConfig:
    config = AlembicConfig(str(RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16", driver="asyncpg") as container:
        yield container


@pytest_asyncio.fixture(scope="session")
async def criar_banco_vazio(postgres):
    """Devolve uma função que cria um banco novo e vazio e responde com a URL dele."""
    url_admin = postgres.get_connection_url()
    motor = create_async_engine(url_admin, isolation_level="AUTOCOMMIT")

    async def criar() -> str:
        nome = f"teste_{uuid.uuid4().hex}"
        async with motor.connect() as conexao:
            await conexao.execute(text(f'CREATE DATABASE "{nome}"'))
        return url_admin.rsplit("/", 1)[0] + "/" + nome

    yield criar
    await motor.dispose()


@pytest_asyncio.fixture
async def banco(criar_banco_vazio):
    url = await criar_banco_vazio()
    await asyncio.to_thread(command.upgrade, config_alembic(url), "head")
    motor = create_async_engine(url)
    async with criar_fabrica_de_sessoes(motor)() as sessao:
        yield sessao
    await motor.dispose()


@pytest.fixture
def config() -> Config:
    return Config(
        database_url="postgresql+asyncpg://u:p@localhost/d",
        jwt_segredo=SEGREDO_DE_TESTE,
        agents_url="http://agentes.invalid",
        agents_token="token-de-teste",
    )


@pytest_asyncio.fixture
async def app(config, criar_banco_vazio):
    """A API ligada a um banco novo, já migrado."""
    url = await criar_banco_vazio()
    await asyncio.to_thread(command.upgrade, config_alembic(url), "head")
    app = criar_app(replace(config, database_url=url))
    yield app
    await app.state.motor.dispose()


@pytest_asyncio.fixture
async def cliente(app):
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        yield c


@pytest.fixture
def entrar_como(cliente):
    """Cadastra (se preciso) e loga; devolve o cabeçalho Authorization."""

    async def entrar(email: str) -> dict:
        corpo = {"email": email, "senha": SENHA_DE_TESTE}
        await cliente.post("/v1/auth/cadastro", json={**corpo, "consentimento": True})
        r = await cliente.post("/v1/auth/login", json=corpo)
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return entrar

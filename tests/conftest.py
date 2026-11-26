import asyncio
import socket
import uuid
from dataclasses import replace

import httpx
import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from artemis_backend.adapters.banco import criar_fabrica_de_sessoes
from artemis_backend.config import Config
from artemis_backend.main import criar_app
from tests.apoio.agentes import AgentesFake
from tests.apoio.banco import config_alembic
from tests.apoio.valores import (
    ANA,
    NOME_DE_TESTE,
    ORIGEM_DE_TESTE,
    SEGREDO_DE_TESTE,
    SENHA_DE_TESTE,
)


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
        origem=ORIGEM_DE_TESTE,
    )


@pytest.fixture
def agentes() -> AgentesFake:
    return AgentesFake()


@pytest.fixture
def porta_fechada() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture
async def app(config, criar_banco_vazio, agentes):
    """A API ligada a um banco novo, já migrado."""
    url = await criar_banco_vazio()
    await asyncio.to_thread(command.upgrade, config_alembic(url), "head")
    app = criar_app(replace(config, database_url=url), agentes)
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
        cadastro = {**corpo, "nome": NOME_DE_TESTE, "consentimento": True}
        await cliente.post("/v1/auth/cadastro", json=cadastro)
        r = await cliente.post("/v1/auth/login", json=corpo)
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return entrar


@pytest_asyncio.fixture
async def sessao(app):
    async with criar_fabrica_de_sessoes(app.state.motor)() as s:
        yield s


@pytest_asyncio.fixture
async def ana(entrar_como):
    return await entrar_como(ANA)


@pytest_asyncio.fixture
async def conversa(cliente, ana) -> str:
    return (await cliente.post("/v1/conversas", headers=ana)).json()["id"]


@pytest.fixture
def perguntar(cliente, ana, conversa):
    async def enviar(pergunta="Quanto ganha uma dev?", id_=conversa, cabecalho=ana):
        return await cliente.post(
            f"/v1/conversas/{id_}/mensagens", headers=cabecalho, json={"pergunta": pergunta}
        )

    return enviar


@pytest.fixture
def mensagens(cliente, ana, conversa):
    async def ler() -> list[dict]:
        return (await cliente.get(f"/v1/conversas/{conversa}", headers=ana)).json()["mensagens"]

    return ler

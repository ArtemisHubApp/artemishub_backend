import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from artemis_backend.adapters.tabelas import Base

config = context.config
URL = config.get_main_option("sqlalchemy.url") or os.environ["DATABASE_URL"]


def _migrar(conexao: Connection) -> None:
    context.configure(connection=conexao, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _rodar() -> None:
    motor = create_async_engine(URL, poolclass=pool.NullPool)
    async with motor.connect() as conexao:
        await conexao.run_sync(_migrar)
    await motor.dispose()


asyncio.run(_rodar())

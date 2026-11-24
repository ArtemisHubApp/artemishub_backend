from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def criar_motor(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url)


def criar_fabrica_de_sessoes(motor: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(motor, expire_on_commit=False)

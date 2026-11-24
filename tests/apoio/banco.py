import uuid

from alembic.config import Config as AlembicConfig
from sqlalchemy import func, select, update

from artemis_backend.adapters.tabelas import Conversa, Mensagem
from tests.apoio.valores import RAIZ


def config_alembic(url: str) -> AlembicConfig:
    config = AlembicConfig(str(RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


async def contar(sessao, tabela, **filtros) -> int:
    consulta = select(func.count()).select_from(tabela)
    for coluna, valor in filtros.items():
        consulta = consulta.where(getattr(tabela, coluna) == valor)
    return await sessao.scalar(consulta)


async def linha(sessao, conversa: str) -> Conversa | None:
    await sessao.rollback()
    return await sessao.scalar(
        select(Conversa)
        .where(Conversa.id == uuid.UUID(conversa))
        .execution_options(populate_existing=True)
    )


async def mudar(sessao, conversa: str, **valores) -> None:
    await sessao.execute(
        update(Conversa).where(Conversa.id == uuid.UUID(conversa)).values(**valores)
    )
    await sessao.commit()


async def total_de_mensagens(sessao) -> int:
    await sessao.rollback()
    return await sessao.scalar(select(func.count()).select_from(Mensagem))

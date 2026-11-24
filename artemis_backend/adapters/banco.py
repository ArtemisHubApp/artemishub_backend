from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import ExceptionContext
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Segundos. Um banco que trava (aceita a conexão e não responde) não pode segurar a requisição.
LIMITE_PARA_CONECTAR = 5
LIMITE_POR_COMANDO = 10


class BancoIndisponivel(Exception):
    """Não deu para falar com o banco: recusou, caiu ou não respondeu a tempo."""


def _conectar(dialeto: Any, _registro: Any, cargs: Any, cparams: Any) -> Any:
    try:
        return dialeto.connect(*cargs, **cparams)
    except (OSError, dialeto.loaded_dbapi.Error):
        raise BancoIndisponivel from None


def _marcar_falha_de_conexao(contexto: ExceptionContext) -> None:
    if isinstance(contexto.original_exception, OSError):
        # Estado desconhecido (TimeoutError também é OSError): a conexão não volta para o pool.
        contexto.is_disconnect = True
    if contexto.is_disconnect and isinstance(contexto.original_exception, Exception):
        raise BancoIndisponivel from None


def criar_motor(database_url: str) -> AsyncEngine:
    motor = create_async_engine(
        database_url,
        hide_parameters=True,
        pool_timeout=LIMITE_PARA_CONECTAR,
        connect_args={"timeout": LIMITE_PARA_CONECTAR, "command_timeout": LIMITE_POR_COMANDO},
    )
    event.listen(motor.sync_engine, "do_connect", _conectar)
    event.listen(motor.sync_engine, "handle_error", _marcar_falha_de_conexao)
    return motor


def criar_fabrica_de_sessoes(motor: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(motor, expire_on_commit=False)

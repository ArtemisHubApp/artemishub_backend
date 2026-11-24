import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from artemis_backend.adapters.tabelas import Usuaria as LinhaUsuaria
from artemis_backend.domain.usuaria import EmailJaCadastrado, Usuaria

_VIOLACAO_DE_UNICIDADE = "23505"


def _para_dominio(linha: LinhaUsuaria) -> Usuaria:
    return Usuaria(
        id=linha.id,
        email=linha.email,
        senha_hash=linha.senha_hash,
        consentiu_em=linha.consentiu_em,
    )


class RepositorioContasSql:
    def __init__(self, sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._sessoes = sessoes

    async def criar(self, usuaria: Usuaria) -> None:
        async with self._sessoes() as sessao:
            sessao.add(
                LinhaUsuaria(
                    id=usuaria.id,
                    email=usuaria.email,
                    senha_hash=usuaria.senha_hash,
                    consentiu_em=usuaria.consentiu_em,
                )
            )
            try:
                await sessao.commit()
            except IntegrityError as erro:
                if getattr(erro.orig, "sqlstate", None) == _VIOLACAO_DE_UNICIDADE:
                    raise EmailJaCadastrado from None
                raise

    async def por_email(self, email: str) -> Usuaria | None:
        async with self._sessoes() as sessao:
            linha = await sessao.scalar(select(LinhaUsuaria).where(LinhaUsuaria.email == email))
        return _para_dominio(linha) if linha else None

    async def por_id(self, id: uuid.UUID) -> Usuaria | None:
        async with self._sessoes() as sessao:
            linha = await sessao.get(LinhaUsuaria, id)
        return _para_dominio(linha) if linha else None

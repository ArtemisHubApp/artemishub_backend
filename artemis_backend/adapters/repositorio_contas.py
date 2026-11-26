import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from artemis_backend.adapters.tabelas import Usuaria as LinhaUsuaria
from artemis_backend.domain.usuaria import EmailJaCadastrado, Usuaria


def _para_dominio(linha: LinhaUsuaria) -> Usuaria:
    return Usuaria(
        id=linha.id,
        nome=linha.nome,
        email=linha.email,
        senha_hash=linha.senha_hash,
        consentiu_em=linha.consentiu_em,
    )


class RepositorioContasSql:
    def __init__(self, sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._sessoes = sessoes

    async def criar(self, usuaria: Usuaria) -> None:
        # ON CONFLICT em vez de capturar a violação: o erro do Postgres levaria o e-mail
        # (DETAIL da violação de unicidade) para o log do servidor.
        comando = (
            insert(LinhaUsuaria)
            .values(
                id=usuaria.id,
                nome=usuaria.nome,
                email=usuaria.email,
                senha_hash=usuaria.senha_hash,
                consentiu_em=usuaria.consentiu_em,
            )
            .on_conflict_do_nothing(index_elements=["email"])
            .returning(LinhaUsuaria.id)
        )
        async with self._sessoes() as sessao:
            gravada = await sessao.scalar(comando)
            await sessao.commit()
        if gravada is None:
            raise EmailJaCadastrado

    async def renomear(self, id: uuid.UUID, nome: str) -> Usuaria | None:
        comando = (
            update(LinhaUsuaria)
            .where(LinhaUsuaria.id == id)
            .values(nome=nome)
            .returning(LinhaUsuaria)
        )
        async with self._sessoes() as sessao:
            linha = await sessao.scalar(comando)
            await sessao.commit()
        return _para_dominio(linha) if linha else None

    async def excluir(self, id: uuid.UUID) -> bool:
        comando = delete(LinhaUsuaria).where(LinhaUsuaria.id == id).returning(LinhaUsuaria.id)
        async with self._sessoes() as sessao:
            apagada = await sessao.scalar(comando)
            await sessao.commit()
        return apagada is not None

    async def por_email(self, email: str) -> Usuaria | None:
        async with self._sessoes() as sessao:
            linha = await sessao.scalar(select(LinhaUsuaria).where(LinhaUsuaria.email == email))
        return _para_dominio(linha) if linha else None

    async def por_id(self, id: uuid.UUID) -> Usuaria | None:
        async with self._sessoes() as sessao:
            linha = await sessao.get(LinhaUsuaria, id)
        return _para_dominio(linha) if linha else None

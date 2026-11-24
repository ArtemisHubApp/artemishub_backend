import uuid

from sqlalchemy import case, delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from artemis_backend.adapters.tabelas import Conversa as LinhaConversa
from artemis_backend.adapters.tabelas import Mensagem as LinhaMensagem
from artemis_backend.domain.conversa import (
    PAPEL_USUARIA,
    Conversa,
    ConversaComMensagens,
    Mensagem,
    UsuariaInexistente,
)

_VIOLACAO_DE_CHAVE_ESTRANGEIRA = "23503"

_COLUNAS_DA_CONVERSA = (
    LinhaConversa.id,
    LinhaConversa.titulo,
    LinhaConversa.criada_em,
    LinhaConversa.atualizada_em,
)


def _conversa(linha) -> Conversa:
    return Conversa(
        id=linha.id,
        titulo=linha.titulo,
        criada_em=linha.criada_em,
        atualizada_em=linha.atualizada_em,
    )


def _mensagem(linha: LinhaMensagem) -> Mensagem:
    return Mensagem(
        id=linha.id,
        papel=linha.papel,
        texto=linha.texto,
        criada_em=linha.criada_em,
        aprovada=linha.aprovada,
        bloqueada=linha.bloqueada,
        trace_id=linha.trace_id,
        pergunta_id=linha.pergunta_id,
    )


class RepositorioConversasSql:
    def __init__(self, sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._sessoes = sessoes

    async def criar(self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID) -> Conversa:
        comando = (
            insert(LinhaConversa)
            .values(id=conversa_id, usuaria_id=usuaria_id)
            .returning(*_COLUNAS_DA_CONVERSA)
        )
        try:
            async with self._sessoes() as sessao, sessao.begin():
                return _conversa((await sessao.execute(comando)).one())
        except IntegrityError as erro:
            if getattr(erro.orig, "sqlstate", None) == _VIOLACAO_DE_CHAVE_ESTRANGEIRA:
                raise UsuariaInexistente from None
            raise

    async def listar(self, usuaria_id: uuid.UUID) -> list[Conversa]:
        consulta = (
            select(*_COLUNAS_DA_CONVERSA)
            .where(LinhaConversa.usuaria_id == usuaria_id)
            .order_by(
                LinhaConversa.atualizada_em.desc(),
                LinhaConversa.criada_em.desc(),
                LinhaConversa.id.desc(),
            )
        )
        async with self._sessoes() as sessao:
            return [_conversa(linha) for linha in await sessao.execute(consulta)]

    async def obter(
        self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID
    ) -> ConversaComMensagens | None:
        # Uma só consulta (conversa e mensagens do mesmo instante), sempre filtrada pela dona.
        consulta = (
            select(LinhaConversa, LinhaMensagem)
            .outerjoin(LinhaMensagem, LinhaMensagem.conversa_id == LinhaConversa.id)
            .where(LinhaConversa.id == conversa_id, LinhaConversa.usuaria_id == usuaria_id)
            .order_by(
                LinhaMensagem.criada_em,
                case((LinhaMensagem.papel == PAPEL_USUARIA, 0), else_=1),
                LinhaMensagem.id,
            )
        )
        async with self._sessoes() as sessao:
            linhas = (await sessao.execute(consulta)).all()
        if not linhas:
            return None
        return ConversaComMensagens(
            conversa=_conversa(linhas[0][0]),
            mensagens=tuple(_mensagem(m) for _, m in linhas if m is not None),
        )

    async def apagar(self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID) -> bool:
        comando = (
            delete(LinhaConversa)
            .where(LinhaConversa.id == conversa_id, LinhaConversa.usuaria_id == usuaria_id)
            .returning(LinhaConversa.id)
        )
        async with self._sessoes() as sessao, sessao.begin():
            return await sessao.scalar(comando) is not None

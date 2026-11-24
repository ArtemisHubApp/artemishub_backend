import uuid
from datetime import datetime
from typing import Any, NoReturn

from sqlalchemy import case, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import Update

from artemis_backend.adapters.tabelas import Conversa as LinhaConversa
from artemis_backend.adapters.tabelas import Mensagem as LinhaMensagem
from artemis_backend.domain.conversa import (
    PAPEL_ARTEMIS,
    PAPEL_USUARIA,
    VALIDADE_DA_TRAVA,
    Conversa,
    ConversaComMensagens,
    ConversaInexistente,
    ConversaOcupada,
    Mensagem,
    NovaResposta,
    PerguntaIniciada,
    UsuariaInexistente,
)

_VIOLACAO_DE_CHAVE_ESTRANGEIRA = "23503"

_COLUNAS_DA_CONVERSA = (
    LinhaConversa.id,
    LinhaConversa.titulo,
    LinhaConversa.criada_em,
    LinhaConversa.atualizada_em,
)


_ORDEM_DAS_MENSAGENS = (
    LinhaMensagem.criada_em,
    case((LinhaMensagem.papel == PAPEL_USUARIA, 0), else_=1),
    LinhaMensagem.id,
)

# now() é o começo da transação, que pode ter esperado pela trava; a ordem das mensagens e a
# atualização da conversa usam o instante em que a linha é gravada.
_INSTANTE = func.clock_timestamp()


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
            .order_by(*_ORDEM_DAS_MENSAGENS)
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

    async def iniciar_pergunta(
        self,
        usuaria_id: uuid.UUID,
        conversa_id: uuid.UUID,
        pergunta_id: uuid.UUID,
        texto: str,
        titulo: str,
    ) -> PerguntaIniciada:
        # Um só UPDATE condicional: entre pedidos simultâneos, o Postgres deixa passar um.
        travar = (
            update(LinhaConversa)
            .where(
                LinhaConversa.id == conversa_id,
                LinhaConversa.usuaria_id == usuaria_id,
                or_(
                    LinhaConversa.respondendo_desde.is_(None),
                    LinhaConversa.respondendo_desde < func.now() - VALIDADE_DA_TRAVA,
                ),
            )
            .values(
                respondendo_desde=func.now(),
                atualizada_em=_INSTANTE,
                titulo=func.coalesce(LinhaConversa.titulo, titulo),
            )
            .returning(LinhaConversa.respondendo_desde, LinhaConversa.lembranca)
        )
        # A conversa já foi conferida e está travada nesta transação; o filtro pela dona segue
        # valendo em toda consulta.
        ler_anteriores = (
            select(LinhaMensagem)
            .join(LinhaConversa, LinhaConversa.id == LinhaMensagem.conversa_id)
            .where(LinhaConversa.id == conversa_id, LinhaConversa.usuaria_id == usuaria_id)
            .order_by(*_ORDEM_DAS_MENSAGENS)
        )
        gravar = (
            insert(LinhaMensagem)
            .values(
                id=pergunta_id,
                conversa_id=conversa_id,
                papel=PAPEL_USUARIA,
                texto=texto,
                criada_em=_INSTANTE,
            )
            .returning(LinhaMensagem)
        )
        async with self._sessoes() as sessao, sessao.begin():
            trava = (await sessao.execute(travar)).one_or_none()
            if trava is None:
                await self._sem_trava(sessao, usuaria_id, conversa_id)
            anteriores = tuple(_mensagem(m) for m in await sessao.scalars(ler_anteriores))
            pergunta = _mensagem((await sessao.scalars(gravar)).one())
        return PerguntaIniciada(pergunta, anteriores, trava.lembranca, trava.respondendo_desde)

    async def concluir_pergunta(
        self,
        usuaria_id: uuid.UUID,
        conversa_id: uuid.UUID,
        respondendo_desde: datetime,
        resposta: NovaResposta,
        lembranca: dict[str, Any] | None,
    ) -> Mensagem:
        valores: dict[str, Any] = {"respondendo_desde": None, "atualizada_em": _INSTANTE}
        if lembranca is not None:
            valores["lembranca"] = lembranca
        soltar = (
            self._se_a_trava_for(usuaria_id, conversa_id, respondendo_desde)
            .values(valores)
            .returning(LinhaConversa.id)
        )
        gravar = (
            insert(LinhaMensagem)
            .values(
                id=resposta.id,
                conversa_id=conversa_id,
                papel=PAPEL_ARTEMIS,
                texto=resposta.texto,
                criada_em=_INSTANTE,
                aprovada=resposta.aprovada,
                bloqueada=resposta.bloqueada,
                trace_id=resposta.trace_id,
                pergunta_id=resposta.pergunta_id,
            )
            .returning(LinhaMensagem)
        )
        async with self._sessoes() as sessao, sessao.begin():
            if await sessao.scalar(soltar) is None:
                await self._sem_trava(sessao, usuaria_id, conversa_id)
            return _mensagem((await sessao.scalars(gravar)).one())

    async def liberar_trava(
        self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID, respondendo_desde: datetime
    ) -> None:
        soltar = self._se_a_trava_for(usuaria_id, conversa_id, respondendo_desde).values(
            respondendo_desde=None
        )
        async with self._sessoes() as sessao, sessao.begin():
            await sessao.execute(soltar)

    @staticmethod
    def _se_a_trava_for(
        usuaria_id: uuid.UUID, conversa_id: uuid.UUID, respondendo_desde: datetime
    ) -> Update:
        return update(LinhaConversa).where(
            LinhaConversa.id == conversa_id,
            LinhaConversa.usuaria_id == usuaria_id,
            LinhaConversa.respondendo_desde == respondendo_desde,
        )

    @staticmethod
    async def _sem_trava(
        sessao: AsyncSession, usuaria_id: uuid.UUID, conversa_id: uuid.UUID
    ) -> NoReturn:
        existe = await sessao.scalar(
            select(LinhaConversa.id).where(
                LinhaConversa.id == conversa_id, LinhaConversa.usuaria_id == usuaria_id
            )
        )
        raise ConversaInexistente if existe is None else ConversaOcupada

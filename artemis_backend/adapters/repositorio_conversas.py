import uuid
from dataclasses import astuple

from sqlalchemy import delete, insert, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from artemis_backend.adapters.linhas_de_conversa import (
    COLUNAS_DA_CONVERSA,
    ORDEM_DAS_MENSAGENS,
    para_conversa,
    para_mensagem,
)
from artemis_backend.adapters.tabelas import Conversa as LinhaConversa
from artemis_backend.adapters.tabelas import Mensagem as LinhaMensagem
from artemis_backend.domain.conversa import (
    Conversa,
    ConversaComMensagens,
    PosicaoNaLista,
    UsuariaInexistente,
)

_VIOLACAO_DE_CHAVE_ESTRANGEIRA = "23503"
# Os campos de PosicaoNaLista, na mesma ordem.
_ORDEM_DA_LISTA = (LinhaConversa.atualizada_em, LinhaConversa.criada_em, LinhaConversa.id)


class RepositorioConversasSql:
    def __init__(self, sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._sessoes = sessoes

    async def criar(self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID) -> Conversa:
        comando = (
            insert(LinhaConversa)
            .values(id=conversa_id, usuaria_id=usuaria_id)
            .returning(*COLUNAS_DA_CONVERSA)
        )
        try:
            async with self._sessoes() as sessao, sessao.begin():
                return para_conversa((await sessao.execute(comando)).one())
        except IntegrityError as erro:
            if getattr(erro.orig, "sqlstate", None) == _VIOLACAO_DE_CHAVE_ESTRANGEIRA:
                raise UsuariaInexistente from None
            raise

    async def listar(
        self, usuaria_id: uuid.UUID, limite: int, depois_de: PosicaoNaLista | None
    ) -> list[Conversa]:
        consulta = (
            select(*COLUNAS_DA_CONVERSA)
            .where(LinhaConversa.usuaria_id == usuaria_id)
            .order_by(*(coluna.desc() for coluna in _ORDEM_DA_LISTA))
            .limit(limite)
        )
        if depois_de is not None:
            consulta = consulta.where(tuple_(*_ORDEM_DA_LISTA) < astuple(depois_de))
        async with self._sessoes() as sessao:
            return [para_conversa(linha) for linha in await sessao.execute(consulta)]

    async def obter(
        self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID
    ) -> ConversaComMensagens | None:
        # Uma só consulta (conversa e mensagens do mesmo instante), sempre filtrada pela dona.
        consulta = (
            select(LinhaConversa, LinhaMensagem)
            .outerjoin(LinhaMensagem, LinhaMensagem.conversa_id == LinhaConversa.id)
            .where(LinhaConversa.id == conversa_id, LinhaConversa.usuaria_id == usuaria_id)
            .order_by(*ORDEM_DAS_MENSAGENS)
        )
        async with self._sessoes() as sessao:
            linhas = (await sessao.execute(consulta)).all()
        if not linhas:
            return None
        return ConversaComMensagens(
            conversa=para_conversa(linhas[0][0]),
            mensagens=tuple(para_mensagem(m) for _, m in linhas if m is not None),
        )

    async def apagar(self, usuaria_id: uuid.UUID, conversa_id: uuid.UUID) -> bool:
        comando = (
            delete(LinhaConversa)
            .where(LinhaConversa.id == conversa_id, LinhaConversa.usuaria_id == usuaria_id)
            .returning(LinhaConversa.id)
        )
        async with self._sessoes() as sessao, sessao.begin():
            return await sessao.scalar(comando) is not None

    async def apagar_todas(self, usuaria_id: uuid.UUID) -> None:
        # O cascade do banco leva as mensagens.
        comando = delete(LinhaConversa).where(LinhaConversa.usuaria_id == usuaria_id)
        async with self._sessoes() as sessao, sessao.begin():
            await sessao.execute(comando)

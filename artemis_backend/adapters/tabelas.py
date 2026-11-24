import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_CASCATA = "CASCADE"


class Base(DeclarativeBase):
    pass


def _agora() -> Any:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Usuaria(Base):
    __tablename__ = "usuarias"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    senha_hash: Mapped[str] = mapped_column(Text)
    criada_em: Mapped[datetime] = _agora()
    consentiu_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Conversa(Base):
    __tablename__ = "conversas"
    __table_args__ = (
        Index("ix_conversas_usuaria_id_atualizada_em", "usuaria_id", "atualizada_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    usuaria_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarias.id", ondelete=_CASCATA))
    titulo: Mapped[str | None] = mapped_column(Text)
    criada_em: Mapped[datetime] = _agora()
    atualizada_em: Mapped[datetime] = _agora()
    lembranca: Mapped[dict | None] = mapped_column(JSONB)
    # Trava de uma resposta por vez na conversa.
    respondendo_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Mensagem(Base):
    __tablename__ = "mensagens"
    __table_args__ = (
        CheckConstraint("papel IN ('usuaria', 'artemis')", name="ck_mensagens_papel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    conversa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversas.id", ondelete=_CASCATA))
    papel: Mapped[str] = mapped_column(Text)
    texto: Mapped[str] = mapped_column(Text)
    criada_em: Mapped[datetime] = _agora()
    aprovada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    bloqueada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    trace_id: Mapped[str | None] = mapped_column(Text)
    # Liga a resposta da Artemis à pergunta que ela respondeu.
    pergunta_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mensagens.id", ondelete=_CASCATA)
    )

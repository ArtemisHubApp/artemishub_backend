"""usuarias, conversas e mensagens

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarias",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("consentiu_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "conversas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "usuaria_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuarias.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo", sa.Text(), nullable=True),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "atualizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("lembranca", postgresql.JSONB(), nullable=True),
        sa.Column("respondendo_desde", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_conversas_usuaria_id_atualizada_em", "conversas", ["usuaria_id", "atualizada_em"]
    )
    op.create_table(
        "mensagens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("papel", sa.Text(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("aprovada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("bloqueada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column(
            "pergunta_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mensagens.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.CheckConstraint("papel IN ('usuaria', 'artemis')", name="ck_mensagens_papel"),
    )


def downgrade() -> None:
    op.drop_table("mensagens")
    op.drop_index("ix_conversas_usuaria_id_atualizada_em", table_name="conversas")
    op.drop_table("conversas")
    op.drop_table("usuarias")

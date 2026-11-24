"""índice em mensagens(conversa_id)

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_mensagens_conversa_id", "mensagens", ["conversa_id"])


def downgrade() -> None:
    op.drop_index("ix_mensagens_conversa_id", table_name="mensagens")

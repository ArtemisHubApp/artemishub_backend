"""nome da usuária

Contas anteriores a esta migração não têm nome; recebem o valor provisório "Usuária" e a
pessoa o troca em PATCH /v1/conta. O valor provisório só vale para elas: contas novas
precisam informar o nome.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuarias", sa.Column("nome", sa.Text(), nullable=False, server_default="Usuária")
    )
    op.alter_column("usuarias", "nome", server_default=None)


def downgrade() -> None:
    op.drop_column("usuarias", "nome")

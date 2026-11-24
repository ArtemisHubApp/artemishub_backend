"""índice em mensagens(pergunta_id)

Sem ele, o cascade da chave estrangeira própria varre a tabela a cada mensagem apagada, e
excluir uma conta com muitas mensagens estoura o limite de tempo do banco.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_mensagens_pergunta_id", "mensagens", ["pergunta_id"])


def downgrade() -> None:
    op.drop_index("ix_mensagens_pergunta_id", table_name="mensagens")

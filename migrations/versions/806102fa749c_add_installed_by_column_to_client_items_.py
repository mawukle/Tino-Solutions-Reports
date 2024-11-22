"""Add installed_by column to client_items table

Revision ID: 806102fa749c
Revises: 86e47c536f0d
Create Date: 2024-11-22 07:10:44.423330

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '806102fa749c'
down_revision = '86e47c536f0d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'client_items',
        sa.Column('installed_by', sa.String(length=50), nullable=False, server_default='Tino Team')
    )

def downgrade():
    op.drop_column('client_items', 'installed_by')

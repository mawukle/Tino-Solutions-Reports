"""Add installed_by column to client_items table

Revision ID: 86e47c536f0d
Revises:
Create Date: 2024-11-20 19:01:35.039463

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '86e47c536f0d'
down_revision = None  # Update this if you have previous migrations
branch_labels = None
depends_on = None


def upgrade():
    """Apply the migration: add `installed_by` column to `client_items` table."""
    op.add_column(
        'client_items',
        sa.Column('installed_by', sa.String(length=50), nullable=False, server_default='Tino Team')
    )
    # Remove the default constraint after data migration if desired
    op.alter_column('client_items', 'installed_by', server_default=None)


def downgrade():
    """Reverse the migration: remove `installed_by` column from `client_items` table."""
    op.drop_column('client_items', 'installed_by')

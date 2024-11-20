"""Create client_items table

Revision ID: 86e47c536f0d
Revises:
Create Date: 2024-11-20 19:01:35.039463

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '86e47c536f0d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create the new `client_items` table
    op.create_table(
        'client_items',
        sa.Column('client_item_id', sa.Integer(), nullable=False),
        sa.Column('client_name', sa.String(length=100), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('component', sa.String(length=255), nullable=False),
        sa.Column('item_description', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('client_item_id')
    )


def downgrade():
    # Drop the `client_items` table if downgrading
    op.drop_table('client_items')

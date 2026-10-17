"""Preserve full prediction-market identifiers in both supported databases."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('records') as table:
        table.alter_column('symbol', existing_type=sa.String(50),
                           type_=sa.String(128), existing_nullable=False)


def downgrade():
    raise RuntimeError('Restore a database backup to revert symbol widening without truncation')

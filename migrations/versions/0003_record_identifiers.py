"""Allow derived provenance identifiers while preserving existing stored IDs."""
from alembic import op
import sqlalchemy as sa
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None
def upgrade():
    with op.batch_alter_table('records') as table:
        table.alter_column('id',existing_type=sa.String(64),type_=sa.String(128),existing_nullable=False)
def downgrade():
    # Refuse a lossy narrowing of existing provenance identifiers.
    raise RuntimeError('Restore a database backup to revert identifier widening')

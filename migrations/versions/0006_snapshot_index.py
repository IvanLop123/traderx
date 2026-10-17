"""Index the profiled prior-day snapshot lookup without caching decisions."""
from alembic import op
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None

def upgrade():op.create_index('ix_records_kind_available','records',['kind','available_at'])
def downgrade():op.drop_index('ix_records_kind_available',table_name='records')

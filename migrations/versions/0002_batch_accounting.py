"""Count actual requests independently of batched document cache entries."""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('llm_runs',sa.Column('call_count',sa.Integer(),nullable=False,server_default='1'))
def downgrade():
    op.drop_column('llm_runs','call_count')

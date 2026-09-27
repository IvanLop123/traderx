"""Initial durable platform schema."""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('records',sa.Column('id',sa.String(64),primary_key=True),sa.Column('kind',sa.String(40),nullable=False),sa.Column('symbol',sa.String(50),nullable=False),sa.Column('created_at',sa.String(40),nullable=False),sa.Column('available_at',sa.String(40),nullable=False),sa.Column('payload',sa.JSON(),nullable=False))
    for column in ['kind','symbol','created_at','available_at']: op.create_index('ix_records_'+column,'records',[column])
    op.create_table('settings',sa.Column('key',sa.String(60),primary_key=True),sa.Column('value',sa.JSON(),nullable=False))
    op.create_table('llm_runs',sa.Column('id',sa.String(64),primary_key=True),sa.Column('cache_key',sa.String(64),unique=True,nullable=False),sa.Column('input_hash',sa.String(64),nullable=False),sa.Column('output_hash',sa.String(64),nullable=False),sa.Column('provider',sa.String(20),nullable=False),sa.Column('model',sa.String(120),nullable=False),sa.Column('module',sa.String(40),nullable=False),sa.Column('prompt_version',sa.String(80),nullable=False),sa.Column('started_at',sa.String(40),nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('input_tokens',sa.Integer(),nullable=False),sa.Column('output_tokens',sa.Integer(),nullable=False),sa.Column('cost',sa.Float(),nullable=False),sa.Column('reserved_cost',sa.Float(),nullable=False),sa.Column('payload',sa.JSON(),nullable=False))
    for column in ['provider','module','started_at']: op.create_index('ix_llm_runs_'+column,'llm_runs',[column])
    op.create_table('jobs',sa.Column('id',sa.String(64),primary_key=True),sa.Column('kind',sa.String(30),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('due_at',sa.String(40),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),sa.Column('error',sa.String(100),nullable=False))
    op.create_index('ix_jobs_state','jobs',['state'])

def downgrade():
    for name in ['jobs','llm_runs','settings','records']: op.drop_table(name)

"""Index measured recent-record reads and retire unused configuration fields.

Records, model artifacts, accounts and experiment payloads remain immutable.
There were no feature-specific futures or conversation tables to drop.
"""
from alembic import op
import sqlalchemy as sa

revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None

def upgrade():
    op.create_index('ix_records_kind_created','records',['kind','created_at'])
    op.create_index('ix_records_kind_symbol_created','records',['kind','symbol','created_at'])
    settings=sa.table('settings',sa.column('key',sa.String),sa.column('value',sa.JSON))
    conn=op.get_bind()
    for key in ('ai','research_universe'):
        value=conn.execute(sa.select(settings.c.value).where(settings.c.key==key)).scalar_one_or_none()
        if not isinstance(value,dict):continue
        if key=='ai':
            value={k:v for k,v in value.items() if k not in ('chat_cloud_enabled','openai_auth_mode')}
        else:
            instruments=[]
            for item in value.get('instruments',[]):
                if item.get('asset_class') not in ('stock','etf','crypto'):
                    raise RuntimeError('Unsupported saved universe instrument: restore/review the private backup before migrating')
                instruments.append({k:v for k,v in item.items() if k not in ('contract_expiration','tick_size','multiplier')})
            value={**value,'instruments':instruments}
        conn.execute(settings.update().where(settings.c.key==key).values(value=value))

def downgrade():
    op.drop_index('ix_records_kind_symbol_created',table_name='records')
    op.drop_index('ix_records_kind_created',table_name='records')

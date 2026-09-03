"""finance cashbox and token bag lifecycle
Revision ID: c8f5d2b0e321
Revises: b7e4c1a9d210
"""
from alembic import op
import sqlalchemy as sa
revision='c8f5d2b0e321'; down_revision='b7e4c1a9d210'; branch_labels=None; depends_on=None
def upgrade():
 op.add_column('token_value_lots',sa.Column('status',sa.String(30),nullable=False,server_default='new')); op.create_index('ix_token_value_lots_status','token_value_lots',['status'])
 for c in ['activated_at','expires_at','expired_at','refunded_at']: op.add_column('token_value_lots',sa.Column(c,sa.DateTime(),nullable=True))
 op.create_index('ix_token_value_lots_expires_at','token_value_lots',['expires_at'])
 op.add_column('token_value_lots',sa.Column('commercial_profit_released',sa.Boolean(),nullable=False,server_default=sa.false()))
 op.add_column('token_value_lots',sa.Column('released_commercial_profit_usd',sa.Numeric(14,6),nullable=False,server_default='0'))
 op.add_column('token_value_lots',sa.Column('released_expiration_usd',sa.Numeric(14,6),nullable=False,server_default='0'))
 op.create_table('finance_withdrawals',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('amount_usd',sa.Numeric(14,6),nullable=False),sa.Column('currency',sa.String(10),nullable=False,server_default='USD'),sa.Column('beneficiary',sa.String(255)),sa.Column('concept',sa.String(255),nullable=False),sa.Column('method',sa.String(100)),sa.Column('proof_url',sa.Text()),sa.Column('notes',sa.Text()),sa.Column('created_by_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),sa.Column('withdrawn_at',sa.DateTime(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False)); op.create_index('ix_finance_withdrawals_created_by_user_id','finance_withdrawals',['created_by_user_id']); op.create_index('ix_finance_withdrawals_withdrawn_at','finance_withdrawals',['withdrawn_at'])
 # Existing lots with consumption are active and release their frozen commercial profit.
 op.execute("UPDATE token_value_lots SET status='active', activated_at=created_at, commercial_profit_released=true WHERE remaining_tokens < original_tokens AND remaining_tokens > 0")
 op.execute("UPDATE token_value_lots SET status='exhausted', activated_at=created_at, commercial_profit_released=true WHERE remaining_tokens <= 0")
def downgrade():
 op.drop_table('finance_withdrawals')
 op.drop_index('ix_token_value_lots_expires_at',table_name='token_value_lots')
 for c in ['released_expiration_usd','released_commercial_profit_usd','commercial_profit_released','refunded_at','expired_at','expires_at','activated_at']: op.drop_column('token_value_lots',c)
 op.drop_index('ix_token_value_lots_status',table_name='token_value_lots'); op.drop_column('token_value_lots','status')

"""add generation financial ledger
Revision ID: 9b7e2c4a1d33
Revises: 8a6d1e4f2b90
"""
from alembic import op
import sqlalchemy as sa
revision='9b7e2c4a1d33'; down_revision='8a6d1e4f2b90'; branch_labels=None; depends_on=None

def upgrade():
    op.create_table('token_value_lots',
      sa.Column('id',sa.Integer(),primary_key=True), sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
      sa.Column('source',sa.String(100),nullable=False), sa.Column('reference_id',sa.String(255)), sa.Column('original_tokens',sa.Integer(),nullable=False),
      sa.Column('remaining_tokens',sa.Integer(),nullable=False), sa.Column('amount_paid_usd',sa.Numeric(14,6),nullable=False,server_default='0'),
      sa.Column('effective_token_value_usd',sa.Numeric(14,9),nullable=False,server_default='0'), sa.Column('metadata_json',sa.Text()), sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_token_value_lots_user_id','token_value_lots',['user_id']); op.create_index('ix_token_value_lots_source','token_value_lots',['source']); op.create_index('ix_token_value_lots_reference_id','token_value_lots',['reference_id']); op.create_index('ix_token_value_lots_created_at','token_value_lots',['created_at'])
    op.execute("INSERT INTO token_value_lots (user_id,source,reference_id,original_tokens,remaining_tokens,amount_paid_usd,effective_token_value_usd,metadata_json,created_at) SELECT id,'legacy_untraced_balance',NULL,token_balance,token_balance,0,0,'{\"traceability\":\"legacy\"}',CURRENT_TIMESTAMP FROM users WHERE token_balance > 0")
    op.create_table('token_consumption_allocations',
      sa.Column('id',sa.Integer(),primary_key=True), sa.Column('execution_id',sa.String(36),nullable=False), sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
      sa.Column('lot_id',sa.Integer(),sa.ForeignKey('token_value_lots.id',ondelete='RESTRICT'),nullable=False), sa.Column('token_transaction_id',sa.Integer(),sa.ForeignKey('token_transactions.id',ondelete='SET NULL')),
      sa.Column('tokens_allocated',sa.Integer(),nullable=False), sa.Column('tokens_reversed',sa.Integer(),nullable=False,server_default='0'), sa.Column('effective_token_value_usd',sa.Numeric(14,9),nullable=False), sa.Column('created_at',sa.DateTime(),nullable=False))
    for c in ['execution_id','user_id','lot_id','token_transaction_id']: op.create_index('ix_token_consumption_allocations_'+c,'token_consumption_allocations',[c])
    op.create_table('generation_financial_records',
      sa.Column('id',sa.Integer(),primary_key=True), sa.Column('execution_id',sa.String(36),nullable=False,unique=True), sa.Column('generation_module_id',sa.Integer(),sa.ForeignKey('generation_modules.id',ondelete='SET NULL')),
      sa.Column('module_key',sa.String(150),nullable=False), sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')), sa.Column('status',sa.String(50),nullable=False), sa.Column('tokens_consumed',sa.Integer(),nullable=False,server_default='0'),
      sa.Column('recognized_revenue_usd',sa.Numeric(14,6),nullable=False,server_default='0'), sa.Column('infrastructure_cost_usd',sa.Numeric(14,6),nullable=False,server_default='0'), sa.Column('gross_profit_usd',sa.Numeric(14,6),nullable=False,server_default='0'),
      sa.Column('gross_margin_percent',sa.Numeric(9,4)), sa.Column('traceability_status',sa.String(30),nullable=False,server_default='exact'), sa.Column('breakdown_json',sa.Text()), sa.Column('created_at',sa.DateTime(),nullable=False), sa.Column('updated_at',sa.DateTime(),nullable=False))
    for c in ['execution_id','generation_module_id','module_key','user_id','status','traceability_status','created_at']: op.create_index('ix_generation_financial_records_'+c,'generation_financial_records',[c],unique=(c=='execution_id'))

def downgrade():
    op.drop_table('generation_financial_records'); op.drop_table('token_consumption_allocations'); op.drop_table('token_value_lots')

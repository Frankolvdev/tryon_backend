"""add profit per token to pricing rules

Revision ID: a4d9f31c7e20
Revises: 9b7e2c4a1d33
"""
from alembic import op
import sqlalchemy as sa
revision="a4d9f31c7e20"
down_revision="9b7e2c4a1d33"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("pricing_rules", sa.Column("desired_profit_per_token_usd", sa.Numeric(18,9), nullable=True))
def downgrade():
    op.drop_column("pricing_rules", "desired_profit_per_token_usd")

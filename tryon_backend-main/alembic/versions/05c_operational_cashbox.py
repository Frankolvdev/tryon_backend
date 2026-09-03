"""operational cashbox and immutable release ledger

Revision ID: 05c_operational_cashbox
Revises: 05b_promo_credits
"""
from alembic import op
import sqlalchemy as sa

revision = "05c_operational_cashbox"
down_revision = "05b_promo_credits"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("token_value_lots", sa.Column("operational_reserve_released", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("token_value_lots", sa.Column("released_operational_reserve_usd", sa.Numeric(14, 6), nullable=False, server_default="0"))
    op.create_table(
        "operational_expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("beneficiary", sa.String(length=255), nullable=True),
        sa.Column("concept", sa.String(length=255), nullable=False),
        sa.Column("method", sa.String(length=100), nullable=True),
        sa.Column("proof_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("spent_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount_usd > 0", name="ck_operational_expense_amount_positive"),
    )
    op.create_index("ix_operational_expenses_category", "operational_expenses", ["category"])
    op.create_index("ix_operational_expenses_created_by_user_id", "operational_expenses", ["created_by_user_id"])
    op.create_index("ix_operational_expenses_spent_at", "operational_expenses", ["spent_at"])


def downgrade():
    op.drop_table("operational_expenses")
    op.drop_column("token_value_lots", "released_operational_reserve_usd")
    op.drop_column("token_value_lots", "operational_reserve_released")

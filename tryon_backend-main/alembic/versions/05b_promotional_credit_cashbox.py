"""promotional credit cashbox

Revision ID: 05b_promo_credits
Revises: 05a_infra_cashbox
"""
from alembic import op
import sqlalchemy as sa

revision = "05b_promo_credits"
down_revision = "05a_infra_cashbox"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "promotional_credit_funds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("original_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("remaining_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("original_usd > 0", name="ck_promo_fund_original_positive"),
        sa.CheckConstraint("remaining_usd >= 0", name="ck_promo_fund_remaining_nonnegative"),
        sa.CheckConstraint("remaining_usd <= original_usd", name="ck_promo_fund_remaining_le_original"),
    )
    op.create_index("ix_promotional_credit_funds_provider", "promotional_credit_funds", ["provider"])
    op.create_index("ix_promotional_credit_funds_created_at", "promotional_credit_funds", ["created_at"])
    op.create_index("ix_promotional_credit_funds_created_by_user_id", "promotional_credit_funds", ["created_by_user_id"])

    op.create_table(
        "promotional_token_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("promotional_credit_funds.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("token_value_lots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tokens_granted", sa.Integer(), nullable=False),
        sa.Column("reserve_per_token_usd", sa.Numeric(14, 9), nullable=False),
        sa.Column("amount_reserved_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("grant_type", sa.String(length=40), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("tokens_granted > 0", name="ck_promo_grant_tokens_positive"),
        sa.CheckConstraint("reserve_per_token_usd > 0", name="ck_promo_grant_reserve_positive"),
        sa.CheckConstraint("amount_reserved_usd > 0", name="ck_promo_grant_amount_positive"),
        sa.UniqueConstraint("lot_id", name="uq_promo_grant_lot"),
    )
    for col in ["fund_id","lot_id","user_id","grant_type","created_by_user_id","created_at"]:
        op.create_index(f"ix_promotional_token_grants_{col}", "promotional_token_grants", [col])

    op.create_table(
        "promotional_credit_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("promotional_credit_funds.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("grant_id", sa.Integer(), sa.ForeignKey("promotional_token_grants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount_usd > 0", name="ck_promo_return_amount_positive"),
        sa.UniqueConstraint("grant_id", "reason", "reference_id", name="uq_promo_return_idempotency"),
    )
    for col in ["fund_id","grant_id","reason","created_at"]:
        op.create_index(f"ix_promotional_credit_returns_{col}", "promotional_credit_returns", [col])


def downgrade():
    op.drop_table("promotional_credit_returns")
    op.drop_table("promotional_token_grants")
    op.drop_table("promotional_credit_funds")

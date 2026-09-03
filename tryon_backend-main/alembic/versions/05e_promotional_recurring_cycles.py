"""add recurring promotional funding cycles

Revision ID: 05e_promo_cycles
Revises: 05d_unused_settings
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "05e_promo_cycles"
down_revision = "05d_unused_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promotional_funding_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False, server_default="recurring_provider"),
        sa.Column("recurrence", sa.String(length=30), nullable=False, server_default="monthly"),
        sa.Column("recurring_amount_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("current_cycle_start", sa.Date(), nullable=False),
        sa.Column("current_cycle_end", sa.Date(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("recurring_amount_usd > 0", name="ck_promo_source_recurring_positive"),
        sa.CheckConstraint("current_cycle_end > current_cycle_start", name="ck_promo_source_cycle_dates"),
    )
    op.create_index("ix_promotional_funding_sources_provider", "promotional_funding_sources", ["provider"])
    op.create_index("ix_promotional_funding_sources_active", "promotional_funding_sources", ["active"])
    op.create_index("ix_promotional_funding_sources_created_by_user_id", "promotional_funding_sources", ["created_by_user_id"])
    op.create_index("ix_promotional_funding_sources_created_at", "promotional_funding_sources", ["created_at"])

    op.create_table(
        "promotional_funding_cycles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("promotional_funding_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("promotional_credit_funds.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("cycle_start", sa.Date(), nullable=False),
        sa.Column("cycle_end", sa.Date(), nullable=False),
        sa.Column("configured_amount_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("opening_available_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("expired_unused_usd", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("returned_after_close_usd", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("cycle_end > cycle_start", name="ck_promo_cycle_dates"),
        sa.CheckConstraint("configured_amount_usd > 0", name="ck_promo_cycle_configured_positive"),
        sa.CheckConstraint("opening_available_usd >= 0", name="ck_promo_cycle_opening_nonnegative"),
        sa.CheckConstraint("expired_unused_usd >= 0", name="ck_promo_cycle_expired_nonnegative"),
        sa.CheckConstraint("returned_after_close_usd >= 0", name="ck_promo_cycle_returned_closed_nonnegative"),
        sa.UniqueConstraint("source_id", "cycle_start", "cycle_end", name="uq_promo_source_cycle_window"),
        sa.UniqueConstraint("fund_id", name="uq_promo_cycle_fund"),
    )
    op.create_index("ix_promotional_funding_cycles_source_id", "promotional_funding_cycles", ["source_id"])
    op.create_index("ix_promotional_funding_cycles_fund_id", "promotional_funding_cycles", ["fund_id"])
    op.create_index("ix_promotional_funding_cycles_cycle_start", "promotional_funding_cycles", ["cycle_start"])
    op.create_index("ix_promotional_funding_cycles_cycle_end", "promotional_funding_cycles", ["cycle_end"])
    op.create_index("ix_promotional_funding_cycles_status", "promotional_funding_cycles", ["status"])
    op.create_index("ix_promotional_funding_cycles_created_at", "promotional_funding_cycles", ["created_at"])


def downgrade() -> None:
    op.drop_table("promotional_funding_cycles")
    op.drop_table("promotional_funding_sources")

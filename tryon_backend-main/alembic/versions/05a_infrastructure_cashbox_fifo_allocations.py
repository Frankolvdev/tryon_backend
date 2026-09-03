"""add infrastructure cashbox funding and FIFO allocation ledger

Revision ID: 05a_infra_cashbox
Revises: d91a4e13b701
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "05a_infra_cashbox"
down_revision = "d91a4e13b701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_funding_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("beneficiary", sa.String(255), nullable=True),
        sa.Column("concept", sa.String(255), nullable=False),
        sa.Column("method", sa.String(100), nullable=True),
        sa.Column("proof_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("funded_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount_usd > 0", name="ck_infra_funding_amount_positive"),
    )
    op.create_index("ix_infra_funding_provider", "infrastructure_funding_movements", ["provider"])
    op.create_index("ix_infra_funding_user", "infrastructure_funding_movements", ["created_by_user_id"])
    op.create_index("ix_infra_funding_at", "infrastructure_funding_movements", ["funded_at"])

    op.create_table(
        "infrastructure_funding_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("movement_id", sa.Integer(), sa.ForeignKey("infrastructure_funding_movements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("token_value_lots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount_usd > 0", name="ck_infra_funding_allocation_positive"),
        sa.UniqueConstraint("movement_id", "lot_id", name="uq_infra_funding_movement_lot"),
    )
    op.create_index("ix_infra_funding_alloc_movement", "infrastructure_funding_allocations", ["movement_id"])
    op.create_index("ix_infra_funding_alloc_lot", "infrastructure_funding_allocations", ["lot_id"])

    op.create_table(
        "infrastructure_provider_credit_releases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("token_value_lots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("funding_allocation_id", sa.Integer(), sa.ForeignKey("infrastructure_funding_allocations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("amount_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False, server_default="token_bag_expiration"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount_usd > 0", name="ck_infra_credit_release_positive"),
        sa.UniqueConstraint("funding_allocation_id", name="uq_infra_credit_release_allocation"),
    )
    op.create_index("ix_infra_credit_release_lot", "infrastructure_provider_credit_releases", ["lot_id"])
    op.create_index("ix_infra_credit_release_alloc", "infrastructure_provider_credit_releases", ["funding_allocation_id"])
    op.create_index("ix_infra_credit_release_provider", "infrastructure_provider_credit_releases", ["provider"])
    op.create_index("ix_infra_credit_release_at", "infrastructure_provider_credit_releases", ["created_at"])


def downgrade() -> None:
    op.drop_table("infrastructure_provider_credit_releases")
    op.drop_table("infrastructure_funding_allocations")
    op.drop_table("infrastructure_funding_movements")

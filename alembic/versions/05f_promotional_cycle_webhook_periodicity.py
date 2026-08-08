"""add promotional cycle webhook simulation flag

Revision ID: 05f_promo_cycle_hook
Revises: 05e_promo_cycles
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "05f_promo_cycle_hook"
down_revision = "05e_promo_cycles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promotional_funding_sources",
        sa.Column("simulation_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("promotional_funding_sources", "simulation_enabled")

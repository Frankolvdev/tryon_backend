"""generation resilience and dynamic pricing

Revision ID: 04a_dyn_pricing_resilience
Revises: 03g_generation_module_endpoint
"""
from alembic import op
import sqlalchemy as sa

revision = "04a_dyn_pricing_resilience"
down_revision = "03g_generation_module_endpoint"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pricing_rules", sa.Column("desired_profit_usd", sa.Numeric(18, 6), nullable=False, server_default="0"))
    op.add_column("pricing_rules", sa.Column("initial_estimated_duration_seconds", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("pricing_rules", sa.Column("technical_margin_seconds", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "provider_gpu_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("gpu_key", sa.String(length=100), nullable=False),
        sa.Column("cost_usd_per_second", sa.Numeric(18, 9), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_provider_gpu_prices_provider", "provider_gpu_prices", ["provider"])
    op.create_index("ix_provider_gpu_prices_gpu_key", "provider_gpu_prices", ["gpu_key"])
    op.create_index("ix_provider_gpu_prices_is_active", "provider_gpu_prices", ["is_active"])
    op.create_index("uq_provider_gpu_prices_provider_gpu", "provider_gpu_prices", ["provider", "gpu_key"], unique=True)


def downgrade():
    op.drop_table("provider_gpu_prices")
    op.drop_column("pricing_rules", "technical_margin_seconds")
    op.drop_column("pricing_rules", "initial_estimated_duration_seconds")
    op.drop_column("pricing_rules", "desired_profit_usd")

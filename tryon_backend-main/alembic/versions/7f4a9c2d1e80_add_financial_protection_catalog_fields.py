"""add financial protection catalog fields

Revision ID: 7f4a9c2d1e80
Revises: 04a_dyn_pricing_resilience
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "7f4a9c2d1e80"
down_revision = "04a_dyn_pricing_resilience"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("token_packages", sa.Column("requested_discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("token_packages", sa.Column("effective_discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("token_packages", sa.Column("nominal_price_cents", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE token_packages SET nominal_price_cents = price_cents WHERE nominal_price_cents = 0")
    op.execute("""
        UPDATE billing_coupons
        SET metadata_json = jsonb_set(
            COALESCE(NULLIF(metadata_json, '')::jsonb, '{}'::jsonb),
            '{applies_to}', '"token_packages"'::jsonb, true
        )::text
        WHERE COALESCE(NULLIF(metadata_json, '')::jsonb ->> 'applies_to', 'all')
              NOT IN ('token_packages', 'free_token_purchase')
    """)


def downgrade():
    op.drop_column("token_packages", "nominal_price_cents")
    op.drop_column("token_packages", "effective_discount_percent")
    op.drop_column("token_packages", "requested_discount_percent")

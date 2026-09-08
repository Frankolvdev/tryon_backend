"""add position to model generation assets

Revision ID: 071_model_asset_position
Revises: 070_model_generation_assets
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "071_model_asset_position"
down_revision = "070_model_generation_assets"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("model_generation_assets", sa.Column("position", sa.Integer(), nullable=True))
    op.create_index("ix_model_generation_assets_position", "model_generation_assets", ["position"], unique=False)

def downgrade() -> None:
    op.drop_index("ix_model_generation_assets_position", table_name="model_generation_assets")
    op.drop_column("model_generation_assets", "position")

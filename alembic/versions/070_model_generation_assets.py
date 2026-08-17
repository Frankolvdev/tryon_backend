"""add generic models ia generation assets

Revision ID: 070_model_generation_assets
Revises: 06f_ancestry_media_assets
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "070_model_generation_assets"
down_revision = "06f_ancestry_media_assets"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_generation_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tool_key", sa.String(length=64), nullable=False),
        sa.Column("asset_key", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Float(), nullable=False, server_default="100"),
        sa.Column("storage_mode", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("poster_storage_file_id", sa.Integer(), sa.ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("video_storage_file_id", sa.Integer(), sa.ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tool_key", "asset_key", name="uq_model_generation_assets_tool_asset"),
    )
    op.create_index("ix_model_generation_assets_tool", "model_generation_assets", ["tool_key"])
    op.create_index("ix_model_generation_assets_asset", "model_generation_assets", ["asset_key"])
    op.create_index("ix_model_generation_assets_sort", "model_generation_assets", ["sort_order"])
    op.create_index("ix_model_generation_assets_active", "model_generation_assets", ["is_active"])


def downgrade():
    op.drop_index("ix_model_generation_assets_active", table_name="model_generation_assets")
    op.drop_index("ix_model_generation_assets_sort", table_name="model_generation_assets")
    op.drop_index("ix_model_generation_assets_asset", table_name="model_generation_assets")
    op.drop_index("ix_model_generation_assets_tool", table_name="model_generation_assets")
    op.drop_table("model_generation_assets")

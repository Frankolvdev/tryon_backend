"""add ancestry media assets

Revision ID: 06f_ancestry_media_assets
Revises: current repository heads (merge + ancestry assets)
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "06f_ancestry_media_assets"
down_revision = ("b7e4c1a9d210", "c8f5d2b0e321", "8a6d1e4f2b90", "06f_ai_model_bubble_butt")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ancestry_media_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ancestry_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=True),
        sa.Column("flag_emoji", sa.String(length=16), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("sort_order", sa.Float(), nullable=False, server_default="100"),
        sa.Column("storage_mode", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("poster_storage_file_id", sa.Integer(), sa.ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("video_storage_file_id", sa.Integer(), sa.ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("ancestry_key", name="uq_ancestry_media_assets_key"),
    )
    op.create_index("ix_ancestry_media_assets_key", "ancestry_media_assets", ["ancestry_key"], unique=True)
    op.create_index("ix_ancestry_media_assets_sort", "ancestry_media_assets", ["sort_order"])
    op.create_index("ix_ancestry_media_assets_active", "ancestry_media_assets", ["is_active"])


def downgrade():
    op.drop_index("ix_ancestry_media_assets_active", table_name="ancestry_media_assets")
    op.drop_index("ix_ancestry_media_assets_sort", table_name="ancestry_media_assets")
    op.drop_index("ix_ancestry_media_assets_key", table_name="ancestry_media_assets")
    op.drop_table("ancestry_media_assets")

"""Extend body proportion tool with base-category metadata and storage mode.

Revision ID: 06b_body_prop_matrix
Revises: 06a_body_prop_tool
"""
from alembic import op
import sqlalchemy as sa

revision = "06b_body_prop_matrix"
down_revision = "06a_body_prop_tool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("body_proportion_workflow_configs", sa.Column("storage_mode", sa.String(length=32), nullable=False, server_default="auto"))
    op.add_column("body_proportion_presets", sa.Column("fat_band", sa.String(length=32), nullable=True))
    op.add_column("body_proportion_presets", sa.Column("ass_band", sa.String(length=32), nullable=True))
    op.add_column("body_proportion_presets", sa.Column("breast_band", sa.String(length=32), nullable=True))
    op.add_column("body_proportion_presets", sa.Column("is_base_category", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("body_proportion_presets", sa.Column("base_category_key", sa.String(length=120), nullable=True))
    op.create_index("ix_body_proportion_presets_fat_band", "body_proportion_presets", ["fat_band"])
    op.create_index("ix_body_proportion_presets_ass_band", "body_proportion_presets", ["ass_band"])
    op.create_index("ix_body_proportion_presets_breast_band", "body_proportion_presets", ["breast_band"])
    op.create_index("ix_body_proportion_presets_is_base_category", "body_proportion_presets", ["is_base_category"])
    op.create_index("ix_body_proportion_presets_base_category_key", "body_proportion_presets", ["base_category_key"])


def downgrade() -> None:
    op.drop_index("ix_body_proportion_presets_base_category_key", table_name="body_proportion_presets")
    op.drop_index("ix_body_proportion_presets_is_base_category", table_name="body_proportion_presets")
    op.drop_index("ix_body_proportion_presets_breast_band", table_name="body_proportion_presets")
    op.drop_index("ix_body_proportion_presets_ass_band", table_name="body_proportion_presets")
    op.drop_index("ix_body_proportion_presets_fat_band", table_name="body_proportion_presets")
    op.drop_column("body_proportion_presets", "base_category_key")
    op.drop_column("body_proportion_presets", "is_base_category")
    op.drop_column("body_proportion_presets", "breast_band")
    op.drop_column("body_proportion_presets", "ass_band")
    op.drop_column("body_proportion_presets", "fat_band")
    op.drop_column("body_proportion_workflow_configs", "storage_mode")

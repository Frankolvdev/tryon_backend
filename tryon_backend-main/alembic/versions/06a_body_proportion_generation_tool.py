"""Add isolated body proportion generation tool tables.

Revision ID: 06a_body_prop_tool
Revises: 05g_module_draft_engine
"""
from alembic import op
import sqlalchemy as sa

revision = "06a_body_prop_tool"
down_revision = "05g_module_draft_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "body_proportion_workflow_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sex", sa.String(length=16), nullable=False),
        sa.Column("workflow_json", sa.JSON(), nullable=True),
        sa.Column("input_mapping_json", sa.JSON(), nullable=False),
        sa.Column("limits_json", sa.JSON(), nullable=False),
        sa.Column("formula_json", sa.JSON(), nullable=False),
        sa.Column("fixed_values_json", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("sex", name="uq_body_proportion_workflow_configs_sex"),
    )
    op.create_index("ix_body_proportion_workflow_configs_id", "body_proportion_workflow_configs", ["id"])
    op.create_index("ix_body_proportion_workflow_configs_sex", "body_proportion_workflow_configs", ["sex"])

    op.create_table(
        "body_proportion_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sex", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Float(), nullable=False),
        sa.Column("profile_key", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=False),
        sa.Column("category_slug", sa.String(length=180), nullable=False),
        sa.Column("hips_size", sa.Float(), nullable=False),
        sa.Column("fat_thin", sa.Float(), nullable=False),
        sa.Column("breasts_size", sa.Float(), nullable=False),
        sa.Column("skin_tone", sa.Float(), nullable=False),
        sa.Column("hair_length", sa.Float(), nullable=False),
        sa.Column("image_storage_file_id", sa.Integer(), sa.ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("local_mirror_path", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("generation_metadata_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("sex", "profile_key", name="uq_body_proportion_preset_sex_key"),
        sa.UniqueConstraint("sex", "category_slug", name="uq_body_proportion_preset_sex_slug"),
    )
    op.create_index("ix_body_proportion_presets_id", "body_proportion_presets", ["id"])
    op.create_index("ix_body_proportion_presets_sex", "body_proportion_presets", ["sex"])
    op.create_index("ix_body_proportion_presets_sort_order", "body_proportion_presets", ["sort_order"])
    op.create_index("ix_body_proportion_presets_image_storage_file_id", "body_proportion_presets", ["image_storage_file_id"])
    op.create_index("ix_body_proportion_presets_status", "body_proportion_presets", ["status"])
    op.create_index("ix_body_proportion_presets_sex_sort", "body_proportion_presets", ["sex", "sort_order"])


def downgrade() -> None:
    op.drop_table("body_proportion_presets")
    op.drop_table("body_proportion_workflow_configs")

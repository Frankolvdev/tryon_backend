"""Add Bubble Butt stage to Body Proportions.

Revision ID: 06e_body_prop_bubble_butt
Revises: 06d_body_prop_preview_library
"""
from alembic import op
import sqlalchemy as sa

revision = "06e_body_prop_bubble_butt"
down_revision = "06d_body_prop_preview_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bubble_butt_workflow_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sex", sa.String(length=16), nullable=False),
        sa.Column("workflow_json", sa.JSON(), nullable=True),
        sa.Column("input_mapping_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("bubble_values_json", sa.JSON(), nullable=False, server_default="[0.0, 0.0, 0.0]"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("sex", name="uq_bubble_butt_workflow_configs_sex"),
    )
    op.create_index("ix_bubble_butt_workflow_configs_id", "bubble_butt_workflow_configs", ["id"])
    op.create_index("ix_bubble_butt_workflow_configs_sex", "bubble_butt_workflow_configs", ["sex"])

    op.create_table(
        "bubble_butt_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sex", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Float(), nullable=False),
        sa.Column("profile_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=220), nullable=False),
        sa.Column("category_slug", sa.String(length=220), nullable=False),
        sa.Column("fat_band", sa.String(length=64), nullable=False),
        sa.Column("ass_band", sa.String(length=64), nullable=False),
        sa.Column("variant_index", sa.Integer(), nullable=False),
        sa.Column("hips_size", sa.Float(), nullable=False),
        sa.Column("fat_thin", sa.Float(), nullable=False),
        sa.Column("breasts_size", sa.Float(), nullable=False),
        sa.Column("bubble_butt", sa.Float(), nullable=False),
        sa.Column("skin_tone", sa.Float(), nullable=False),
        sa.Column("hair_length", sa.Float(), nullable=False),
        sa.Column("image_storage_file_id", sa.Integer(), sa.ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("preview_storage_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("local_mirror_path", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("generation_metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("sex", "profile_key", name="uq_bubble_butt_preset_sex_key"),
        sa.UniqueConstraint("sex", "fat_band", "ass_band", "variant_index", name="uq_bubble_butt_grid"),
    )
    op.create_index("ix_bubble_butt_presets_id", "bubble_butt_presets", ["id"])
    op.create_index("ix_bubble_butt_presets_sex", "bubble_butt_presets", ["sex"])
    op.create_index("ix_bubble_butt_presets_sort_order", "bubble_butt_presets", ["sort_order"])
    op.create_index("ix_bubble_butt_presets_fat_band", "bubble_butt_presets", ["fat_band"])
    op.create_index("ix_bubble_butt_presets_ass_band", "bubble_butt_presets", ["ass_band"])
    op.create_index("ix_bubble_butt_presets_variant_index", "bubble_butt_presets", ["variant_index"])
    op.create_index("ix_bubble_butt_presets_status", "bubble_butt_presets", ["status"])
    op.create_index("ix_bubble_butt_presets_image_storage_file_id", "bubble_butt_presets", ["image_storage_file_id"])
    op.create_index("ix_bubble_butt_presets_sex_sort", "bubble_butt_presets", ["sex", "sort_order"])


def downgrade() -> None:
    op.drop_table("bubble_butt_presets")
    op.drop_table("bubble_butt_workflow_configs")

"""Add multi-source preview library for Body Proportions.

Revision ID: 06d_body_prop_preview_library
Revises: 06c_ai_model_profiles
"""
from alembic import op
import sqlalchemy as sa

revision = "06d_body_prop_preview_library"
down_revision = "06c_ai_model_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "body_proportion_workflow_configs",
        sa.Column("active_preview_source", sa.String(length=32), nullable=False, server_default="auto"),
    )
    op.add_column(
        "body_proportion_presets",
        sa.Column("preview_storage_json", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("body_proportion_presets", "preview_storage_json")
    op.drop_column("body_proportion_workflow_configs", "active_preview_source")

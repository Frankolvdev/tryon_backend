"""Persist selected Bubble Butt on AI model profiles.

Revision ID: 06f_ai_model_bubble_butt
Revises: 06e_body_prop_bubble_butt
"""
from alembic import op
import sqlalchemy as sa

revision = "06f_ai_model_bubble_butt"
down_revision = "06e_body_prop_bubble_butt"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "ai_model_profiles",
        sa.Column(
            "bubble_butt_preset_id",
            sa.Integer(),
            sa.ForeignKey("bubble_butt_presets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ai_model_profiles_bubble_butt_preset_id",
        "ai_model_profiles",
        ["bubble_butt_preset_id"],
    )

def downgrade() -> None:
    op.drop_index("ix_ai_model_profiles_bubble_butt_preset_id", table_name="ai_model_profiles")
    op.drop_column("ai_model_profiles", "bubble_butt_preset_id")

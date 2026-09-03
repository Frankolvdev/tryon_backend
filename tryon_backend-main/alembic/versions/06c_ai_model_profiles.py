"""add ai model profiles

Revision ID: 06c_ai_model_profiles
Revises: 06b_body_prop_matrix
"""
from alembic import op
import sqlalchemy as sa

revision = "06c_ai_model_profiles"
down_revision = "06b_body_prop_matrix"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "ai_model_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sex", sa.String(length=16), nullable=False, server_default="woman"),
        sa.Column("body_proportion_preset_id", sa.Integer(), sa.ForeignKey("body_proportion_presets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="body"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_ai_model_profiles_user_name"),
    )
    op.create_index("ix_ai_model_profiles_user_id", "ai_model_profiles", ["user_id"])
    op.create_index("ix_ai_model_profiles_sex", "ai_model_profiles", ["sex"])
    op.create_index("ix_ai_model_profiles_body_preset", "ai_model_profiles", ["body_proportion_preset_id"])
    op.create_index("ix_ai_model_profiles_stage", "ai_model_profiles", ["stage"])

def downgrade():
    op.drop_table("ai_model_profiles")

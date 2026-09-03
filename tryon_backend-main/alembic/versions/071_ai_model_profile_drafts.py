"""persist ai model creation drafts

Revision ID: 071_ai_model_profile_drafts
Revises: 070_model_generation_assets
"""
from alembic import op
import sqlalchemy as sa

revision = "071_ai_model_profile_drafts"
down_revision = "070_model_generation_assets"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("ai_model_profiles", sa.Column("draft_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

def downgrade():
    op.drop_column("ai_model_profiles", "draft_json")

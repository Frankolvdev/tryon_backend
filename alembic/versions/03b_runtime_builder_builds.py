"""runtime builder build and deploy history
Revision ID: 03b_runtime_builder
Revises: 03a_runtime_builder
"""
from alembic import op
import sqlalchemy as sa
revision = "03b_runtime_builder"
down_revision = "03a_runtime_builder"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("runtime_builder_builds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("runtime_config_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("image_tag", sa.String(500), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("phase", sa.String(64), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("logs", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("context_path", sa.String(1000), nullable=True),
        sa.Column("image_id", sa.String(255), nullable=True),
        sa.Column("image_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("validation_result", sa.JSON(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for name, cols in [("ix_runtime_builder_builds_id",["id"]),("ix_runtime_builder_builds_runtime_config_id",["runtime_config_id"]),("ix_runtime_builder_builds_version",["version"]),("ix_runtime_builder_builds_image_tag",["image_tag"]),("ix_runtime_builder_builds_status",["status"]),("ix_runtime_builder_builds_active",["active"])]:
        op.create_index(name,"runtime_builder_builds",cols)

def downgrade():
    op.drop_table("runtime_builder_builds")

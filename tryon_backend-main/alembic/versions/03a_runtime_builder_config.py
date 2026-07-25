"""add runtime builder configuration

Revision ID: 03a_runtime_builder
Revises: 02c_pricing_title
"""
from alembic import op
import sqlalchemy as sa

revision = "03a_runtime_builder"
down_revision = "02c_pricing_title"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runtime_builder_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="Runtime principal"),
        sa.Column("runtime_version", sa.String(length=64), nullable=False, server_default="1.0.0"),
        sa.Column("python_version", sa.String(length=32), nullable=False, server_default="3.11"),
        sa.Column("cuda_version", sa.String(length=32), nullable=False, server_default="12.4.1"),
        sa.Column("pytorch_index_url", sa.String(length=1000), nullable=False, server_default="https://download.pytorch.org/whl/cu124"),
        sa.Column("comfyui_repository", sa.String(length=1000), nullable=False, server_default="https://github.com/comfyanonymous/ComfyUI.git"),
        sa.Column("comfyui_commit", sa.String(length=128), nullable=True),
        sa.Column("target_platform", sa.String(length=64), nullable=False, server_default="linux/amd64"),
        sa.Column("registry_image", sa.String(length=500), nullable=False, server_default="ghcr.io/your-org/tryon-generation-runtime"),
        sa.Column("include_comfyui_manager", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("custom_nodes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("python_dependencies", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("models", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("environment_variables", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("volumes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_runtime_builder_configs_id", "runtime_builder_configs", ["id"])
    op.create_index("ix_runtime_builder_configs_is_active", "runtime_builder_configs", ["is_active"])


def downgrade():
    op.drop_index("ix_runtime_builder_configs_is_active", table_name="runtime_builder_configs")
    op.drop_index("ix_runtime_builder_configs_id", table_name="runtime_builder_configs")
    op.drop_table("runtime_builder_configs")

"""runtime builder project workspace

Revision ID: 03d_runtime_project
Revises: 03c_runtime_workspace
"""
from alembic import op
import sqlalchemy as sa

revision = "03d_runtime_project"
down_revision = "03c_runtime_workspace"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("runtime_builder_configs", sa.Column("project_key", sa.String(length=120), nullable=False, server_default="tryon"))
    op.add_column("runtime_builder_configs", sa.Column("module_type", sa.String(length=120), nullable=False, server_default="tryon"))
    op.add_column("runtime_builder_configs", sa.Column("container_workdir", sa.String(length=1000), nullable=False, server_default="/app"))
    op.add_column("runtime_builder_configs", sa.Column("export_root_directory", sa.String(length=2000), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("workspace_status", sa.String(length=64), nullable=False, server_default="draft"))
    op.create_index("ix_runtime_builder_configs_project_key", "runtime_builder_configs", ["project_key"], unique=False)
    op.create_index("ix_runtime_builder_configs_module_type", "runtime_builder_configs", ["module_type"], unique=False)

def downgrade():
    op.drop_index("ix_runtime_builder_configs_module_type", table_name="runtime_builder_configs")
    op.drop_index("ix_runtime_builder_configs_project_key", table_name="runtime_builder_configs")
    for name in ["workspace_status", "export_root_directory", "container_workdir", "module_type", "project_key"]:
        op.drop_column("runtime_builder_configs", name)

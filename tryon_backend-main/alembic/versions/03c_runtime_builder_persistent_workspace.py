"""runtime builder persistent workspace

Revision ID: 03c_runtime_builder_persistent_workspace
Revises: 03b_runtime_builder_builds
"""
from alembic import op
import sqlalchemy as sa

revision = "03c_runtime_workspace"
down_revision = "03b_runtime_builder"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("runtime_builder_configs", sa.Column("source_comfyui_path", sa.String(length=2000), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("workflow_filename", sa.String(length=500), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("workflow_json", sa.JSON(), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("last_index_summary", sa.JSON(), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("export_directory", sa.String(length=2000), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("last_export_archive", sa.String(length=2000), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("last_export_manifest", sa.JSON(), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("last_exported_at", sa.DateTime(), nullable=True))

def downgrade():
    for name in ["last_exported_at","last_export_manifest","last_export_archive","export_directory","last_index_summary","workflow_json","workflow_filename","source_comfyui_path"]:
        op.drop_column("runtime_builder_configs", name)

"""persistent runtime projects

Revision ID: 03e_runtime_projects
Revises: 03d_runtime_project
"""
from alembic import op
import sqlalchemy as sa

revision = "03e_runtime_projects"
down_revision = "03d_runtime_project"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runtime_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("runtime_config_id", sa.Integer(), nullable=True),
        sa.Column("project_key", sa.String(length=120), nullable=False),
        sa.Column("module_type", sa.String(length=120), nullable=False),
        sa.Column("source_comfyui_path", sa.String(length=2000), nullable=True),
        sa.Column("workflow_filename", sa.String(length=500), nullable=True),
        sa.Column("workflow_json", sa.JSON(), nullable=True),
        sa.Column("container_workdir", sa.String(length=1000), nullable=False, server_default="/app"),
        sa.Column("export_root_directory", sa.String(length=2000), nullable=True),
        sa.Column("export_directory", sa.String(length=2000), nullable=True),
        sa.Column("last_index_summary", sa.JSON(), nullable=True),
        sa.Column("workspace_status", sa.String(length=64), nullable=False, server_default="draft"),
        sa.Column("last_export_archive", sa.String(length=2000), nullable=True),
        sa.Column("last_export_manifest", sa.JSON(), nullable=True),
        sa.Column("last_exported_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_key", name="uq_runtime_projects_project_key"),
    )
    op.create_index("ix_runtime_projects_id", "runtime_projects", ["id"])
    op.create_index("ix_runtime_projects_runtime_config_id", "runtime_projects", ["runtime_config_id"])
    op.create_index("ix_runtime_projects_project_key", "runtime_projects", ["project_key"])
    op.create_index("ix_runtime_projects_module_type", "runtime_projects", ["module_type"])
    op.execute("""
        INSERT INTO runtime_projects (
            runtime_config_id, project_key, module_type, source_comfyui_path,
            workflow_filename, workflow_json, container_workdir,
            export_root_directory, export_directory, last_index_summary,
            workspace_status, last_export_archive, last_export_manifest,
            last_exported_at, created_at, updated_at
        )
        SELECT id, COALESCE(project_key, 'tryon'), COALESCE(module_type, 'tryon'),
               source_comfyui_path, workflow_filename, workflow_json,
               COALESCE(container_workdir, '/app'), export_root_directory,
               export_directory, last_index_summary, COALESCE(workspace_status, 'draft'),
               last_export_archive, last_export_manifest, last_exported_at,
               created_at, updated_at
        FROM runtime_builder_configs
        ORDER BY id ASC
        LIMIT 1
    """)


def downgrade():
    op.drop_index("ix_runtime_projects_module_type", table_name="runtime_projects")
    op.drop_index("ix_runtime_projects_project_key", table_name="runtime_projects")
    op.drop_index("ix_runtime_projects_runtime_config_id", table_name="runtime_projects")
    op.drop_index("ix_runtime_projects_id", table_name="runtime_projects")
    op.drop_table("runtime_projects")

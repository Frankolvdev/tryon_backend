"""create persistent runtime projects

Revision ID: 03e_runtime_projects
Revises: 03d_runtime_project
"""

from alembic import op
import sqlalchemy as sa

revision = "03e_runtime_projects"
down_revision = "03d_runtime_project"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    # This guard makes the migration safe when a developer created the table
    # manually while troubleshooting, while Alembic was still at revision 03d.
    if not _table_exists("runtime_projects"):
        op.create_table(
            "runtime_projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("runtime_config_id", sa.Integer(), nullable=True),
            sa.Column("project_key", sa.String(length=120), nullable=False),
            sa.Column("module_type", sa.String(length=120), nullable=False),
            sa.Column("source_comfyui_path", sa.String(length=2000), nullable=True),
            sa.Column("workflow_filename", sa.String(length=500), nullable=True),
            sa.Column("workflow_json", sa.JSON(), nullable=True),
            sa.Column(
                "container_workdir",
                sa.String(length=1000),
                nullable=False,
                server_default=sa.text("'/app'"),
            ),
            sa.Column("export_root_directory", sa.String(length=2000), nullable=True),
            sa.Column("export_directory", sa.String(length=2000), nullable=True),
            sa.Column("last_index_summary", sa.JSON(), nullable=True),
            sa.Column(
                "workspace_status",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'draft'"),
            ),
            sa.Column("last_export_archive", sa.String(length=2000), nullable=True),
            sa.Column("last_export_manifest", sa.JSON(), nullable=True),
            sa.Column("last_exported_at", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("project_key", name="uq_runtime_projects_project_key"),
        )

    for index_name, columns in (
        ("ix_runtime_projects_id", ["id"]),
        ("ix_runtime_projects_runtime_config_id", ["runtime_config_id"]),
        ("ix_runtime_projects_project_key", ["project_key"]),
        ("ix_runtime_projects_module_type", ["module_type"]),
    ):
        if not _index_exists("runtime_projects", index_name):
            op.create_index(index_name, "runtime_projects", columns, unique=False)

    # Preserve the workspace that existed in runtime_builder_configs before
    # RuntimeProject was introduced. ON CONFLICT keeps this operation idempotent.
    if _table_exists("runtime_builder_configs"):
        op.execute(
            sa.text(
                """
                INSERT INTO runtime_projects (
                    runtime_config_id,
                    project_key,
                    module_type,
                    source_comfyui_path,
                    workflow_filename,
                    workflow_json,
                    container_workdir,
                    export_root_directory,
                    export_directory,
                    last_index_summary,
                    workspace_status,
                    last_export_archive,
                    last_export_manifest,
                    last_exported_at,
                    created_at,
                    updated_at
                )
                SELECT
                    id,
                    COALESCE(project_key, 'tryon'),
                    COALESCE(module_type, 'tryon'),
                    source_comfyui_path,
                    workflow_filename,
                    workflow_json,
                    COALESCE(container_workdir, '/app'),
                    export_root_directory,
                    export_directory,
                    last_index_summary,
                    COALESCE(workspace_status, 'draft'),
                    last_export_archive,
                    last_export_manifest,
                    last_exported_at,
                    COALESCE(created_at, CURRENT_TIMESTAMP),
                    COALESCE(updated_at, CURRENT_TIMESTAMP)
                FROM runtime_builder_configs
                ORDER BY id ASC
                LIMIT 1
                ON CONFLICT (project_key) DO NOTHING
                """
            )
        )


def downgrade() -> None:
    if not _table_exists("runtime_projects"):
        return

    for index_name in (
        "ix_runtime_projects_module_type",
        "ix_runtime_projects_project_key",
        "ix_runtime_projects_runtime_config_id",
        "ix_runtime_projects_id",
    ):
        if _index_exists("runtime_projects", index_name):
            op.drop_index(index_name, table_name="runtime_projects")

    op.drop_table("runtime_projects")

"""runtime name and universal gpu defaults

Revision ID: 03f_runtime_name_gpu
Revises: 03e_runtime_projects
"""
from alembic import op
import sqlalchemy as sa

revision = "03f_runtime_name_gpu"
down_revision = "03e_runtime_projects"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("runtime_builder_configs", sa.Column("runtime_name", sa.String(length=120), nullable=False, server_default="generation-runtime"))
    op.create_index("ix_runtime_builder_configs_runtime_name", "runtime_builder_configs", ["runtime_name"], unique=False)
    op.execute("UPDATE runtime_builder_configs SET cuda_version='12.8.0', pytorch_index_url='https://download.pytorch.org/whl/cu128' WHERE cuda_version IN ('12.4','12.4.0','12.4.1')")
    op.execute("UPDATE runtime_builder_configs SET registry_image=REPLACE(registry_image, 'tryon-generation-runtime', 'generation-runtime')")

def downgrade():
    op.drop_index("ix_runtime_builder_configs_runtime_name", table_name="runtime_builder_configs")
    op.drop_column("runtime_builder_configs", "runtime_name")

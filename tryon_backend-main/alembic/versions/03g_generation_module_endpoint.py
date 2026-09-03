"""generation module endpoint

Revision ID: 03g_generation_module_endpoint
Revises: 03f_runtime_name_gpu
"""
from alembic import op
import sqlalchemy as sa
revision="03g_generation_module_endpoint"
down_revision="03f_runtime_name_gpu"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("generation_modules", sa.Column("endpoint", sa.String(length=500), nullable=True))
    op.add_column("runtime_builder_configs", sa.Column("provider", sa.String(length=50), nullable=False, server_default="modal"))
    op.create_index("ix_runtime_builder_configs_provider", "runtime_builder_configs", ["provider"], unique=False)
    op.create_index("ix_generation_modules_endpoint", "generation_modules", ["endpoint"], unique=False)
def downgrade():
    op.drop_index("ix_runtime_builder_configs_provider", table_name="runtime_builder_configs")
    op.drop_column("runtime_builder_configs", "provider")
    op.drop_index("ix_generation_modules_endpoint", table_name="generation_modules")
    op.drop_column("generation_modules", "endpoint")

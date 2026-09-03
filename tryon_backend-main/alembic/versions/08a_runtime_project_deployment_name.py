"""add per-runtime deployment name

Revision ID: 08a_runtime_deployment_name
Revises: 8a6d1e4f2b90
"""
from alembic import op
import sqlalchemy as sa

revision = "08a_runtime_deployment_name"
down_revision = "8a6d1e4f2b90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "runtime_projects",
        sa.Column("deployment_name", sa.String(length=120), nullable=True),
    )


def downgrade():
    op.drop_column("runtime_projects", "deployment_name")

"""persist selected runtime validated profile

Revision ID: 08b_runtime_validated_profile_id
Revises: 08a_runtime_deployment_name
"""
from alembic import op
import sqlalchemy as sa


revision = "08b_runtime_validated_profile_id"
down_revision = "08a_runtime_deployment_name"
branch_labels = None
depends_on = None


LEGACY_ID = "universal-legacy-2026-02"
MODERN_ID = "universal-modern-2026-08"


def upgrade():
    op.add_column(
        "runtime_builder_configs",
        sa.Column(
            "validated_profile_id",
            sa.String(length=64),
            nullable=False,
            server_default=LEGACY_ID,
        ),
    )
    # Preserve already-selected Modern runtimes when upgrading existing data.
    op.execute(
        sa.text(
            """
            UPDATE runtime_builder_configs
               SET validated_profile_id = :modern_id
             WHERE python_version = '3.10.20'
               AND cuda_version = '13.0.0'
               AND pytorch_index_url = 'https://download.pytorch.org/whl/cu130'
               AND comfyui_commit = 'v0.31.0'
            """
        ).bindparams(modern_id=MODERN_ID)
    )
    op.alter_column(
        "runtime_builder_configs",
        "validated_profile_id",
        server_default=None,
    )


def downgrade():
    op.drop_column("runtime_builder_configs", "validated_profile_id")

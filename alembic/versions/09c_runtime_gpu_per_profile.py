"""runtime gpu per profile

Revision ID: 09c_runtime_gpu_per_profile
Revises: 08b_runtime_validated_profile_id
"""
from alembic import op
import sqlalchemy as sa

revision = "09c_runtime_gpu_per_profile"
down_revision = "08b_runtime_validated_profile_id"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("runtime_builder_configs", sa.Column("gpu", sa.String(length=120), nullable=False, server_default="L40S"))
    # Preserve the current global Modal choice for existing runtimes when possible.
    op.execute("""
        UPDATE runtime_builder_configs
        SET gpu = COALESCE((
            SELECT value_string FROM system_settings WHERE key = 'modal_gpu' LIMIT 1
        ), 'L40S')
        WHERE provider = 'modal'
    """)

def downgrade():
    op.drop_column("runtime_builder_configs", "gpu")

"""remove unused legacy system settings

Revision ID: 05d_unused_settings
Revises: 05c_operational_cashbox
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "05d_unused_settings"
down_revision = "05c_operational_cashbox"
branch_labels = None
depends_on = None

# These keys were audited against the current backend/backoffice source and
# have no runtime consumer. Public/contract settings are deliberately excluded.
UNUSED_KEYS = (
    "app_environment",
    "max_login_attempts",
    "password_min_length",
    "active_payment_provider",
    "monthly_tokens_reset_enabled",
    "dynamic_pricing_enabled",
    "default_margin_percent",
    "scheduler_timezone",
    "analytics_enabled",
    "log_retention_days",
    "commercial_currency",
)


def upgrade() -> None:
    system_settings = sa.table("system_settings", sa.column("key", sa.String()))
    op.execute(system_settings.delete().where(system_settings.c.key.in_(UNUSED_KEYS)))


def downgrade() -> None:
    # Intentionally do not recreate obsolete placeholders. Downgrading the
    # application code can seed its own historical defaults if needed.
    pass

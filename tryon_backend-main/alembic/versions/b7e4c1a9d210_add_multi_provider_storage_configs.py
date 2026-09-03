"""add independent Amazon S3 and Cloudflare R2 integration configs

Revision ID: b7e4c1a9d210
Revises: a4d9f31c7e20
"""
from alembic import op
import sqlalchemy as sa

revision = "b7e4c1a9d210"
down_revision = "a4d9f31c7e20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    now = sa.func.now()
    rows = [
        {
            "provider": "amazon_s3",
            "name": "Amazon S3",
            "config_json": '{"bucket":"","region":"","endpoint_url":"","public_base_url":"","addressing_style":"virtual"}',
        },
        {
            "provider": "cloudflare_r2",
            "name": "Cloudflare R2",
            "config_json": '{"account_id":"","bucket":"","endpoint_url":"","public_base_url":"","addressing_style":"path"}',
        },
    ]
    for row in rows:
        exists = bind.execute(sa.text("SELECT 1 FROM integration_configs WHERE provider=:provider"), {"provider": row["provider"]}).first()
        if not exists:
            bind.execute(sa.text("""
                INSERT INTO integration_configs
                (provider, name, status, is_enabled, base_url, api_key, api_secret, webhook_secret,
                 config_json, last_health_status, last_health_message, last_checked_at, created_at, updated_at)
                VALUES (:provider, :name, 'disabled', false, NULL, NULL, NULL, NULL,
                        :config_json, NULL, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """), row)


def downgrade() -> None:
    op.execute("DELETE FROM integration_configs WHERE provider IN ('amazon_s3', 'cloudflare_r2')")

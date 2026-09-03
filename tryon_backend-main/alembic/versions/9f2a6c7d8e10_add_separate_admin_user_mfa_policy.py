"""add separate admin and user MFA policy

Revision ID: 9f2a6c7d8e10
Revises: 22a5cd2a04fc
Create Date: 2026-07-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f2a6c7d8e10"
down_revision: Union[str, Sequence[str], None] = "22a5cd2a04fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_security_settings",
        sa.Column(
            "admin_mfa_totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "account_security_settings",
        sa.Column(
            "admin_mfa_recovery_codes_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "account_security_settings",
        sa.Column(
            "user_mfa_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "account_security_settings",
        sa.Column(
            "user_mfa_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "account_security_settings",
        sa.Column(
            "user_mfa_totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "account_security_settings",
        sa.Column(
            "user_mfa_recovery_codes_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.alter_column(
        "account_security_settings",
        "admin_mfa_totp_enabled",
        server_default=None,
    )
    op.alter_column(
        "account_security_settings",
        "admin_mfa_recovery_codes_enabled",
        server_default=None,
    )
    op.alter_column(
        "account_security_settings",
        "user_mfa_available",
        server_default=None,
    )
    op.alter_column(
        "account_security_settings",
        "user_mfa_required",
        server_default=None,
    )
    op.alter_column(
        "account_security_settings",
        "user_mfa_totp_enabled",
        server_default=None,
    )
    op.alter_column(
        "account_security_settings",
        "user_mfa_recovery_codes_enabled",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column(
        "account_security_settings",
        "user_mfa_recovery_codes_enabled",
    )
    op.drop_column(
        "account_security_settings",
        "user_mfa_totp_enabled",
    )
    op.drop_column(
        "account_security_settings",
        "user_mfa_required",
    )
    op.drop_column(
        "account_security_settings",
        "user_mfa_available",
    )
    op.drop_column(
        "account_security_settings",
        "admin_mfa_recovery_codes_enabled",
    )
    op.drop_column(
        "account_security_settings",
        "admin_mfa_totp_enabled",
    )

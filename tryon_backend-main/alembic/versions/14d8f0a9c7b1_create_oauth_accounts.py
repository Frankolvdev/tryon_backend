"""create oauth accounts

Revision ID: 14d8f0a9c7b1
Revises: e981094ef7c1
Create Date: 2026-07-20

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "14d8f0a9c7b1"
down_revision: Union[str, None] = "e981094ef7c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=255), nullable=True),
        sa.Column("provider_username", sa.String(length=255), nullable=True),
        sa.Column("provider_avatar_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "last_login_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_oauth_accounts_provider_identity",
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            name="uq_oauth_accounts_user_provider",
        ),
    )

    op.create_index(
        op.f("ix_oauth_accounts_id"),
        "oauth_accounts",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_accounts_provider"),
        "oauth_accounts",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_accounts_provider_email"),
        "oauth_accounts",
        ["provider_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_accounts_provider_user_id"),
        "oauth_accounts",
        ["provider_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_accounts_user_id"),
        "oauth_accounts",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_oauth_accounts_user_id"),
        table_name="oauth_accounts",
    )
    op.drop_index(
        op.f("ix_oauth_accounts_provider_user_id"),
        table_name="oauth_accounts",
    )
    op.drop_index(
        op.f("ix_oauth_accounts_provider_email"),
        table_name="oauth_accounts",
    )
    op.drop_index(
        op.f("ix_oauth_accounts_provider"),
        table_name="oauth_accounts",
    )
    op.drop_index(
        op.f("ix_oauth_accounts_id"),
        table_name="oauth_accounts",
    )
    op.drop_table("oauth_accounts")

"""prepare users for social auth

Revision ID: a0f33c86e526
Revises: b122765b4da2
Create Date: 2026-07-08 16:19:28.689169
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a0f33c86e526"
down_revision: Union[str, None] = "b122765b4da2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=50),
            nullable=True,
            server_default="email",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "provider_user_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.execute("UPDATE users SET auth_provider = 'email' WHERE auth_provider IS NULL")

    op.alter_column(
        "users",
        "auth_provider",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=None,
    )

    op.create_index(
        "ix_users_auth_provider",
        "users",
        ["auth_provider"],
        unique=False,
    )

    op.create_index(
        "ix_users_provider_user_id",
        "users",
        ["provider_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_provider_user_id", table_name="users")
    op.drop_index("ix_users_auth_provider", table_name="users")
    op.drop_column("users", "provider_user_id")
    op.drop_column("users", "auth_provider")
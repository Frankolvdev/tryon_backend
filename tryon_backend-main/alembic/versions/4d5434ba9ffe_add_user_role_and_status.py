"""add user role and status

Revision ID: 4d5434ba9ffe
Revises: a0f33c86e526
Create Date: 2026-07-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d5434ba9ffe"
down_revision: Union[str, None] = "a0f33c86e526"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=50), nullable=True, server_default="user"),
    )

    op.add_column(
        "users",
        sa.Column("status", sa.String(length=50), nullable=True, server_default="active"),
    )

    op.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
    op.execute("UPDATE users SET status = 'active' WHERE status IS NULL")

    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=None,
    )

    op.alter_column(
        "users",
        "status",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=None,
    )

    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_status", "users", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "status")
    op.drop_column("users", "role")
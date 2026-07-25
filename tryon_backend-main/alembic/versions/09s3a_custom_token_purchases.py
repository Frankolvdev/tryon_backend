"""allow custom token purchases without a package

Revision ID: 09s3a_custom_tokens
Revises: 14d8f0a9c7b1
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "09s3a_custom_tokens"
down_revision: Union[str, Sequence[str], None] = "14d8f0a9c7b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "token_purchases",
        "token_package_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Custom purchases have no package and cannot be represented by the old
    # schema. Refuse a silent destructive downgrade until they are migrated.
    op.alter_column(
        "token_purchases",
        "token_package_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

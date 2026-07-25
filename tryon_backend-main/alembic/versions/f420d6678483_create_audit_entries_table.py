"""create audit entries table

Revision ID: f420d6678483
Revises: ca110057b06e
Create Date: 2026-07-12 13:53:31.578247

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f420d6678483'
down_revision: Union[str, Sequence[str], None] = 'ca110057b06e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

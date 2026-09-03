"""create audit entries table

Revision ID: 60be102b7d8d
Revises: f420d6678483
Create Date: 2026-07-12 13:54:01.068090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60be102b7d8d'
down_revision: Union[str, Sequence[str], None] = 'f420d6678483'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

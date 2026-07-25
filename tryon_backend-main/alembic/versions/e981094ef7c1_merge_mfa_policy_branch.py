"""merge mfa policy branch

Revision ID: e981094ef7c1
Revises: 2c9d6b13291d, 9f2a6c7d8e10
Create Date: 2026-07-15 18:57:26.570736

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e981094ef7c1'
down_revision: Union[str, Sequence[str], None] = ('2c9d6b13291d', '9f2a6c7d8e10')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

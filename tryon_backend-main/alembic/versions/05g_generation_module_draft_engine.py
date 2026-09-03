"""Allow generation modules to exist as drafts without an execution engine.

Revision ID: 05g_module_draft_engine
Revises: 05f_promo_cycle_hook
"""

from alembic import op
import sqlalchemy as sa

revision = "05g_module_draft_engine"
down_revision = "05f_promo_cycle_hook"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "generation_modules",
        "default_execution_engine",
        existing_type=sa.String(length=50),
        nullable=True,
        existing_nullable=False,
    )


def downgrade() -> None:
    # Draft modules have no engine. For a safe downgrade, keep their disabled
    # semantics while restoring the historical non-null placeholder.
    op.execute(
        "UPDATE generation_modules "
        "SET default_execution_engine = 'simulated' "
        "WHERE default_execution_engine IS NULL"
    )
    op.alter_column(
        "generation_modules",
        "default_execution_engine",
        existing_type=sa.String(length=50),
        nullable=False,
        existing_nullable=True,
    )

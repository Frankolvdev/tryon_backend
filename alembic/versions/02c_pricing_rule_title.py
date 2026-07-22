"""add pricing rule title

Revision ID: 02c_pricing_title
Revises: 02b_gen_exec_history
"""

from alembic import op
import sqlalchemy as sa

revision = "02c_pricing_title"
down_revision = "02b_gen_exec_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pricing_rules", sa.Column("title", sa.String(length=255), nullable=True))
    op.execute("UPDATE pricing_rules SET title = 'Regla de pricing ' || id WHERE title IS NULL")
    op.alter_column("pricing_rules", "title", nullable=False)
    op.create_index(op.f("ix_pricing_rules_title"), "pricing_rules", ["title"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pricing_rules_title"), table_name="pricing_rules")
    op.drop_column("pricing_rules", "title")

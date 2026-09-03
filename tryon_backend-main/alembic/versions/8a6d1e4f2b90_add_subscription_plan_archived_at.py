"""add explicit subscription plan archive state

Revision ID: 8a6d1e4f2b90
Revises: 7f4a9c2d1e80
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa


revision = "8a6d1e4f2b90"
down_revision = "7f4a9c2d1e80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_subscription_plans_archived_at",
        "subscription_plans",
        ["archived_at"],
        unique=False,
    )

    # Recover plans archived by the previous safe-delete hotfix.  Requiring a
    # subscription reference prevents ordinary inactive/private drafts from
    # being mistaken for deleted plans.
    op.execute(
        """
        UPDATE subscription_plans AS plan
        SET archived_at = CURRENT_TIMESTAMP
        WHERE plan.is_active = FALSE
          AND plan.is_public = FALSE
          AND plan.archived_at IS NULL
          AND EXISTS (
              SELECT 1
              FROM user_subscriptions AS subscription
              WHERE subscription.subscription_plan_id = plan.id
          )
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscription_plans_archived_at",
        table_name="subscription_plans",
    )
    op.drop_column("subscription_plans", "archived_at")

"""persist generation module execution history

Revision ID: 02b_generation_module_execution_history
Revises: 02a_generation_modules
Create Date: 2026-07-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "02b_generation_module_execution_history"
down_revision: Union[str, Sequence[str], None] = "02a_generation_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_module_executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("generation_module_id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=150), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("engine", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["generation_module_id"], ["generation_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_generation_module_executions_public_id", "generation_module_executions", ["public_id"], unique=True)
    op.create_index("ix_generation_module_executions_generation_module_id", "generation_module_executions", ["generation_module_id"])
    op.create_index("ix_generation_module_executions_module_key", "generation_module_executions", ["module_key"])
    op.create_index("ix_generation_module_executions_user_id", "generation_module_executions", ["user_id"])
    op.create_index("ix_generation_module_executions_engine", "generation_module_executions", ["engine"])
    op.create_index("ix_generation_module_executions_status", "generation_module_executions", ["status"])
    op.create_index("ix_generation_module_executions_created_at", "generation_module_executions", ["created_at"])
    op.create_index("ix_generation_module_executions_finished_at", "generation_module_executions", ["finished_at"])
    op.create_index("ix_generation_module_executions_user_created", "generation_module_executions", ["user_id", "created_at"])
    op.create_index("ix_generation_module_executions_module_status", "generation_module_executions", ["generation_module_id", "status"])
    op.create_index("ix_generation_module_executions_status_updated", "generation_module_executions", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_table("generation_module_executions")

"""add generation modules foundation

Revision ID: 02a_generation_modules
Revises: 09s3a_custom_tokens
Create Date: 2026-07-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "02a_generation_modules"
down_revision: Union[str, Sequence[str], None] = "09s3a_custom_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("default_execution_engine", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_modules_id"), "generation_modules", ["id"], unique=False)
    op.create_index(op.f("ix_generation_modules_key"), "generation_modules", ["key"], unique=False)
    op.create_index(op.f("ix_generation_modules_category"), "generation_modules", ["category"], unique=False)
    op.create_index(op.f("ix_generation_modules_default_execution_engine"), "generation_modules", ["default_execution_engine"], unique=False)
    op.create_index(op.f("ix_generation_modules_is_active"), "generation_modules", ["is_active"], unique=False)
    op.create_index(op.f("ix_generation_modules_created_by_user_id"), "generation_modules", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_generation_modules_created_at"), "generation_modules", ["created_at"], unique=False)
    op.create_index("ix_generation_modules_key_version", "generation_modules", ["key", "version"], unique=True)
    op.create_index("ix_generation_modules_category_active", "generation_modules", ["category", "is_active"], unique=False)

    op.create_table(
        "generation_module_inputs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation_module_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_type", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("default_value_json", sa.Text(), nullable=True),
        sa.Column("validation_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["generation_module_id"], ["generation_modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_module_inputs_id"), "generation_module_inputs", ["id"], unique=False)
    op.create_index(op.f("ix_generation_module_inputs_generation_module_id"), "generation_module_inputs", ["generation_module_id"], unique=False)
    op.create_index("ix_generation_module_inputs_module_key", "generation_module_inputs", ["generation_module_id", "key"], unique=True)
    op.create_index("ix_generation_module_inputs_module_position", "generation_module_inputs", ["generation_module_id", "position"], unique=False)

    op.create_table(
        "generation_module_outputs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation_module_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("output_type", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("source_step_key", sa.String(length=150), nullable=True),
        sa.Column("source_path", sa.String(length=500), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["generation_module_id"], ["generation_modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_module_outputs_id"), "generation_module_outputs", ["id"], unique=False)
    op.create_index(op.f("ix_generation_module_outputs_generation_module_id"), "generation_module_outputs", ["generation_module_id"], unique=False)
    op.create_index("ix_generation_module_outputs_module_key", "generation_module_outputs", ["generation_module_id", "key"], unique=True)
    op.create_index("ix_generation_module_outputs_module_position", "generation_module_outputs", ["generation_module_id", "position"], unique=False)

    op.create_table(
        "generation_module_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation_module_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("step_type", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("input_mapping_json", sa.Text(), nullable=False),
        sa.Column("output_mapping_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["generation_module_id"], ["generation_modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_module_steps_id"), "generation_module_steps", ["id"], unique=False)
    op.create_index(op.f("ix_generation_module_steps_generation_module_id"), "generation_module_steps", ["generation_module_id"], unique=False)
    op.create_index("ix_generation_module_steps_module_key", "generation_module_steps", ["generation_module_id", "key"], unique=True)
    op.create_index("ix_generation_module_steps_module_position", "generation_module_steps", ["generation_module_id", "position"], unique=True)

    op.add_column("pricing_rules", sa.Column("generation_module_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_pricing_rules_generation_module_id"), "pricing_rules", ["generation_module_id"], unique=False)
    op.create_foreign_key(
        "fk_pricing_rules_generation_module_id",
        "pricing_rules",
        "generation_modules",
        ["generation_module_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_pricing_rules_generation_module_id", "pricing_rules", type_="foreignkey")
    op.drop_index(op.f("ix_pricing_rules_generation_module_id"), table_name="pricing_rules")
    op.drop_column("pricing_rules", "generation_module_id")

    op.drop_index("ix_generation_module_steps_module_position", table_name="generation_module_steps")
    op.drop_index("ix_generation_module_steps_module_key", table_name="generation_module_steps")
    op.drop_index(op.f("ix_generation_module_steps_generation_module_id"), table_name="generation_module_steps")
    op.drop_index(op.f("ix_generation_module_steps_id"), table_name="generation_module_steps")
    op.drop_table("generation_module_steps")

    op.drop_index("ix_generation_module_outputs_module_position", table_name="generation_module_outputs")
    op.drop_index("ix_generation_module_outputs_module_key", table_name="generation_module_outputs")
    op.drop_index(op.f("ix_generation_module_outputs_generation_module_id"), table_name="generation_module_outputs")
    op.drop_index(op.f("ix_generation_module_outputs_id"), table_name="generation_module_outputs")
    op.drop_table("generation_module_outputs")

    op.drop_index("ix_generation_module_inputs_module_position", table_name="generation_module_inputs")
    op.drop_index("ix_generation_module_inputs_module_key", table_name="generation_module_inputs")
    op.drop_index(op.f("ix_generation_module_inputs_generation_module_id"), table_name="generation_module_inputs")
    op.drop_index(op.f("ix_generation_module_inputs_id"), table_name="generation_module_inputs")
    op.drop_table("generation_module_inputs")

    op.drop_index("ix_generation_modules_category_active", table_name="generation_modules")
    op.drop_index("ix_generation_modules_key_version", table_name="generation_modules")
    op.drop_index(op.f("ix_generation_modules_created_at"), table_name="generation_modules")
    op.drop_index(op.f("ix_generation_modules_created_by_user_id"), table_name="generation_modules")
    op.drop_index(op.f("ix_generation_modules_is_active"), table_name="generation_modules")
    op.drop_index(op.f("ix_generation_modules_default_execution_engine"), table_name="generation_modules")
    op.drop_index(op.f("ix_generation_modules_category"), table_name="generation_modules")
    op.drop_index(op.f("ix_generation_modules_key"), table_name="generation_modules")
    op.drop_index(op.f("ix_generation_modules_id"), table_name="generation_modules")
    op.drop_table("generation_modules")

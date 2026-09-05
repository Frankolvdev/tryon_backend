"""make generation-module pricing rules reusable

Revision ID: 06g_reusable_module_pricing
Revises: 06f_ai_model_bubble_butt
"""

from alembic import op
import sqlalchemy as sa

revision = "06g_reusable_module_pricing"
down_revision = "06f_ai_model_bubble_butt"
branch_labels = None
depends_on = None


def _signature(row):
    return (
        row.operation_type,
        row.item_type,
        row.quality_mode,
        row.tokens_cost,
        row.estimated_gpu_seconds,
        row.estimated_gpu_cost_cents,
        row.margin_percent,
        row.desired_profit_usd,
        row.desired_profit_per_token_usd,
        row.initial_estimated_duration_seconds,
        row.technical_margin_seconds,
        bool(row.is_active),
    )


def upgrade():
    op.add_column(
        "generation_modules",
        sa.Column("pricing_rule_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_generation_modules_pricing_rule_id",
        "generation_modules",
        ["pricing_rule_id"],
    )
    op.create_foreign_key(
        "fk_generation_modules_pricing_rule_id",
        "generation_modules",
        "pricing_rules",
        ["pricing_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()
    meta = sa.MetaData()
    modules = sa.Table("generation_modules", meta, autoload_with=bind)
    rules = sa.Table("pricing_rules", meta, autoload_with=bind)

    module_rows = {
        int(row.id): row
        for row in bind.execute(sa.select(modules)).mappings().all()
    }
    rule_rows = [
        row for row in bind.execute(sa.select(rules)).mappings().all()
    ]
    rules_by_id = {int(row.id): row for row in rule_rows}

    # Index potential source rules by exact title + exact financial configuration.
    by_title_signature = {}
    for row in rule_rows:
        by_title_signature.setdefault(
            (str(row.title), _signature(row)), []
        ).append(row)

    def canonical_rule(row):
        """Collapse only copies provably created by the old module-copy mechanism."""
        current = row
        visited = set()
        copied_ids = []
        while current is not None and int(current.id) not in visited:
            visited.add(int(current.id))
            owner_id = current.generation_module_id
            owner = module_rows.get(int(owner_id)) if owner_id is not None else None
            if owner is None:
                break
            suffix = " · " + str(owner.name)
            title = str(current.title)
            if not title.endswith(suffix):
                break
            source_title = title[:-len(suffix)]
            candidates = [
                candidate
                for candidate in by_title_signature.get(
                    (source_title, _signature(current)), []
                )
                if int(candidate.id) < int(current.id)
            ]
            if not candidates:
                break
            source = max(candidates, key=lambda item: int(item.id))
            copied_ids.append(int(current.id))
            current = source
        return current, copied_ids

    # Preserve the exact legacy winner semantics: active first, then newest id.
    rules_by_module = {}
    for row in rule_rows:
        if row.generation_module_id is None:
            continue
        module_id = int(row.generation_module_id)
        current = rules_by_module.get(module_id)
        rank = (1 if bool(row.is_active) else 0, int(row.id))
        if current is None or rank > current[0]:
            rules_by_module[module_id] = (rank, row)

    proven_copy_ids = set()
    for module_id, (_rank, legacy_rule) in rules_by_module.items():
        canonical, copied_ids = canonical_rule(legacy_rule)
        if canonical is None:
            canonical = legacy_rule
        bind.execute(
            modules.update()
            .where(modules.c.id == module_id)
            .values(pricing_rule_id=int(canonical.id))
        )
        proven_copy_ids.update(copied_ids)

    # Old module-owned copies are retained for audit/history but hidden from normal
    # active-rule selection. Nothing is deleted and no financial value is changed.
    if proven_copy_ids:
        bind.execute(
            rules.update()
            .where(rules.c.id.in_(sorted(proven_copy_ids)))
            .values(is_active=False)
        )

    # The old column becomes legacy-only. Clearing it removes the exclusivity
    # semantics while preserving every pricing-rule row and every numeric value.
    bind.execute(rules.update().values(generation_module_id=None))


def downgrade():
    bind = op.get_bind()
    meta = sa.MetaData()
    modules = sa.Table("generation_modules", meta, autoload_with=bind)
    rules = sa.Table("pricing_rules", meta, autoload_with=bind)

    # Legacy schema can represent at most one module per pricing rule. Restore one
    # deterministic owner for downgrade compatibility without cloning any rule.
    rows = bind.execute(
        sa.select(modules.c.id, modules.c.pricing_rule_id)
        .where(modules.c.pricing_rule_id.is_not(None))
        .order_by(modules.c.id.asc())
    ).all()
    claimed = set()
    for module_id, rule_id in rows:
        if int(rule_id) in claimed:
            continue
        bind.execute(
            rules.update()
            .where(rules.c.id == int(rule_id))
            .values(generation_module_id=int(module_id))
        )
        claimed.add(int(rule_id))

    op.drop_constraint(
        "fk_generation_modules_pricing_rule_id",
        "generation_modules",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_generation_modules_pricing_rule_id",
        table_name="generation_modules",
    )
    op.drop_column("generation_modules", "pricing_rule_id")

import hashlib
import json
import re
import io
import mimetypes
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath
from uuid import uuid4
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import StorageProvider
from app.common.time import utc_now
from app.core.config import settings
from app.models.body_proportion_tool import BodyProportionPreset, BodyProportionWorkflowConfig, BubbleButtPreset
from app.models.storage_file import StorageFile
from app.schemas.body_proportion_tool import DEFAULT_FIXED_VALUES, DEFAULT_FORMULA, DEFAULT_LIMITS
from app.services.comfyui_local_adapter_service import comfyui_local_adapter_service
from app.services.storage_service import storage_service


class BodyProportionToolService:
    SEXES = {"woman", "man"}
    STORAGE_MODES = {"auto", "local", "amazon_s3", "cloudflare_r2"}
    PATCH_KEYS = ("hips_size", "fat_thin", "breasts_size", "skin_tone", "hair_length", "category_name", "sex")

    @staticmethod
    def _deep_merge(base: dict, override: dict | None) -> dict:
        result = deepcopy(base)
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = BodyProportionToolService._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    @staticmethod
    def _ordered_levels(levels: dict, value_key: str, *, reverse: bool = False) -> list[str]:
        return sorted(
            levels.keys(),
            key=lambda key: (
                float((levels.get(key) or {}).get("order", 0.0)),
                float((levels.get(key) or {}).get(value_key, 0.0)),
                key,
            ),
            reverse=reverse,
        )

    def _formula_orders(self, formula: dict) -> tuple[list[str], list[str], list[str]]:
        fat_order = self._ordered_levels(formula.get("fat_levels") or {}, "body_fat_percent")
        ass_order = self._ordered_levels(formula.get("ass_levels") or {}, "hips_size")
        breast_order = self._ordered_levels(formula.get("breast_levels") or {}, "base")
        return fat_order, ass_order, breast_order

    def _normalize_formula(self, formula: dict) -> dict:
        normalized = self._deep_merge(DEFAULT_FORMULA, formula)
        # Transparently upgrade only the two legacy built-in defaults. Custom values
        # different from the old defaults are never touched.
        fat_levels = normalized.get("fat_levels") or {}
        if float((fat_levels.get("low") or {}).get("fat_thin", 0.8)) == 1.0:
            fat_levels["low"]["fat_thin"] = 0.8
        if float((fat_levels.get("high") or {}).get("fat_thin", -0.5)) == -1.0:
            fat_levels["high"]["fat_thin"] = -0.5
        if float((fat_levels.get("very_high") or {}).get("fat_thin", -1.0)) == -1.4:
            fat_levels["very_high"]["fat_thin"] = -1.0
        breast_levels = normalized.get("breast_levels") or {}
        if float((breast_levels.get("big") or {}).get("base", 0.9)) == 1.0:
            breast_levels["big"]["base"] = 0.9
        if float((breast_levels.get("huge") or {}).get("base", 1.8)) == 1.5:
            breast_levels["huge"]["base"] = 1.8
        fat_order, ass_order, breast_order = self._formula_orders(normalized)
        matrix = normalized.setdefault("ass_breast_compensation", {})
        for ass_key in ass_order:
            row = matrix.setdefault(ass_key, {})
            for breast_key in breast_order:
                row.setdefault(breast_key, 0.0)
        return normalized

    @staticmethod
    def _normalize_limits(limits: dict | None) -> dict:
        normalized = BodyProportionToolService._deep_merge(DEFAULT_LIMITS, limits or {})
        # Upgrade only legacy built-in maximums. Custom values are preserved.
        if normalized.get("breasts_max") is not None and float(normalized["breasts_max"]) in {1.5, 1.8}:
            normalized["breasts_max"] = 3.0
        return normalized

    def _validate_formula(self, formula: dict, limits: dict) -> dict:
        formula = self._normalize_formula(formula)
        fat_order, ass_order, breast_order = self._formula_orders(formula)
        if len(fat_order) < 2 or len(ass_order) < 2 or len(breast_order) < 2:
            raise ValueError("At least two fat, glute and breast anchors are required.")

        def strictly(values: list[float], increasing: bool, label: str) -> None:
            for left, right in zip(values, values[1:]):
                if increasing and not left < right:
                    raise ValueError(f"{label} anchors must be strictly increasing.")
                if not increasing and not left > right:
                    raise ValueError(f"{label} anchors must be strictly decreasing.")

        fat_percents = [float(formula["fat_levels"][key].get("body_fat_percent", 0.0)) for key in fat_order]
        fat_values = [float(formula["fat_levels"][key]["fat_thin"]) for key in fat_order]
        hips = [float(formula["ass_levels"][key]["hips_size"]) for key in ass_order]
        breasts = [float(formula["breast_levels"][key]["base"]) for key in breast_order]

        strictly(fat_percents, True, "Body-fat percentage")
        strictly(fat_values, False, "fat_thin")
        strictly(hips, True, "Glute")
        strictly(breasts, True, "Breast")

        hips_min, hips_max = limits.get("hips_min"), limits.get("hips_max")
        breast_min, breast_max = limits.get("breasts_min"), limits.get("breasts_max")
        fat_min, fat_max = limits.get("fat_thin_min"), limits.get("fat_thin_max")
        for value in hips:
            if hips_min is not None and value < float(hips_min): raise ValueError("Glute anchor is below hips_min.")
            if hips_max is not None and value > float(hips_max): raise ValueError("Glute anchor exceeds hips_max.")
        for value in breasts:
            if breast_min is not None and value < float(breast_min): raise ValueError("Breast anchor is below breasts_min.")
            if breast_max is not None and value > float(breast_max): raise ValueError("Breast anchor exceeds breasts_max.")
        for value in fat_values:
            if fat_min is not None and value < float(fat_min): raise ValueError("fat_thin anchor is below fat_thin_min.")
            if fat_max is not None and value > float(fat_max): raise ValueError("fat_thin anchor exceeds fat_thin_max.")
        return formula

    def _validate_sex(self, sex: str) -> str:
        normalized = str(sex).strip().lower()
        if normalized not in self.SEXES:
            raise ValueError("sex must be woman or man")
        return normalized

    def _validate_storage_mode(self, mode: str | None) -> str:
        value = str(mode or "auto").strip().lower()
        if value not in self.STORAGE_MODES:
            raise ValueError(f"Unsupported storage mode: {value}")
        return value

    def _default_config(self, sex: str) -> dict:
        return {
            "id": None,
            "sex": sex,
            "workflow": None,
            "input_mapping": {},
            "limits": deepcopy(DEFAULT_LIMITS),
            "formula": deepcopy(DEFAULT_FORMULA),
            "fixed_values": deepcopy(DEFAULT_FIXED_VALUES),
            "storage_mode": "auto",
            "active_preview_source": "auto",
            "is_enabled": False,
            "notes": None,
            "created_at": None,
            "updated_at": None,
        }

    def get_config(self, db: Session, sex: str) -> dict:
        sex = self._validate_sex(sex)
        row = db.execute(select(BodyProportionWorkflowConfig).where(BodyProportionWorkflowConfig.sex == sex)).scalar_one_or_none()
        if not row:
            return self._default_config(sex)
        return {
            "id": row.id,
            "sex": row.sex,
            "workflow": row.workflow_json,
            "input_mapping": row.input_mapping_json or {},
            "limits": self._normalize_limits(row.limits_json),
            "formula": self._normalize_formula(row.formula_json or {}),
            "fixed_values": self._deep_merge(DEFAULT_FIXED_VALUES, row.fixed_values_json),
            "storage_mode": self._validate_storage_mode(getattr(row, "storage_mode", "auto")),
            "active_preview_source": self._validate_storage_mode(getattr(row, "active_preview_source", "auto")),
            "is_enabled": bool(row.is_enabled),
            "notes": row.notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def upsert_config(self, db: Session, sex: str, data) -> dict:
        sex = self._validate_sex(sex)
        row = db.execute(select(BodyProportionWorkflowConfig).where(BodyProportionWorkflowConfig.sex == sex)).scalar_one_or_none()
        limits = self._normalize_limits(data.limits)
        formula = self._validate_formula(data.formula, limits)
        payload = {
            "workflow_json": data.workflow,
            "input_mapping_json": data.input_mapping,
            "limits_json": limits,
            "formula_json": formula,
            "fixed_values_json": self._deep_merge(DEFAULT_FIXED_VALUES, data.fixed_values),
            "storage_mode": self._validate_storage_mode(data.storage_mode),
            "is_enabled": bool(data.is_enabled),
            "notes": data.notes,
        }
        if row is None:
            row = BodyProportionWorkflowConfig(sex=sex, **payload)
            db.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        db.commit(); db.refresh(row)
        self.write_configuration_manifest(db, sex)
        return self.get_config(db, sex)

    @staticmethod
    def _slug(value: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
        return value or "profile"

    def _next_sort_order(self, db: Session, sex: str) -> float:
        value = db.execute(select(func.max(BodyProportionPreset.sort_order)).where(BodyProportionPreset.sex == sex)).scalar_one_or_none()
        return float(value or 0.0) + 100.0

    def _next_identity(self, db: Session, sex: str) -> tuple[str, str]:
        count = db.execute(select(func.count()).select_from(BodyProportionPreset).where(BodyProportionPreset.sex == sex)).scalar_one()
        prefix = "W" if sex == "woman" else "M"
        number = int(count) + 1
        while True:
            key = f"{prefix}-P{number:03d}"
            exists = db.execute(select(BodyProportionPreset.id).where(BodyProportionPreset.sex == sex, BodyProportionPreset.profile_key == key)).scalar_one_or_none()
            if not exists:
                return key, f"profile_{number:03d}"
            number += 1

    def _assert_limits(self, config: dict, values: dict) -> None:
        limits = config["limits"]
        checks = (
            ("hips_size", "hips_min", "hips_max"),
            ("breasts_size", "breasts_min", "breasts_max"),
            ("fat_thin", "fat_thin_min", "fat_thin_max"),
            ("skin_tone", "skin_tone_min", "skin_tone_max"),
        )
        for field, low_key, high_key in checks:
            value = float(values[field])
            low, high = limits.get(low_key), limits.get(high_key)
            if low is not None and value < float(low):
                raise ValueError(f"{field}={value} is below configured minimum {low}.")
            if high is not None and value > float(high):
                raise ValueError(f"{field}={value} exceeds configured maximum {high}.")

    def _base_values(self, config: dict, fat_band: str, ass_band: str, breast_band: str) -> dict:
        formula = config["formula"]
        fat = formula["fat_levels"][fat_band]
        ass = formula["ass_levels"][ass_band]
        breast = formula["breast_levels"][breast_band]
        ass_breast = (formula.get("ass_breast_compensation") or {}).get(ass_band, {}).get(breast_band, 0.0)
        hips = float(ass["hips_size"]) + float(fat.get("hips_compensation", 0.0))
        breasts = float(breast["base"]) + float(ass_breast) + float(fat.get("breasts_compensation", 0.0))
        values = {
            "hips_size": round(hips, 4),
            "fat_thin": round(float(fat["fat_thin"]), 4),
            "breasts_size": round(breasts, 4),
            "skin_tone": float(config["fixed_values"].get("skin_tone", 0.0)),
            "hair_length": float(config["fixed_values"].get("hair_length", 0.0)),
        }
        self._assert_limits(config, values)
        return values

    def _base_name(self, config: dict, fat_band: str, ass_band: str, breast_band: str) -> str:
        f = config["formula"]
        return f'{f["fat_levels"][fat_band]["label"]} - {f["ass_levels"][ass_band]["label"]} - {f["breast_levels"][breast_band]["label"]}'

    @staticmethod
    def _base_key(fat_band: str, ass_band: str, breast_band: str) -> str:
        return f"{fat_band}:{ass_band}:{breast_band}"

    def seed_defaults(self, db: Session, sex: str) -> dict:
        sex = self._validate_sex(sex)
        config = self.get_config(db, sex)
        formula = self._validate_formula(config["formula"], config["limits"])
        fat_order, ass_order, breast_order = self._formula_orders(formula)
        expected = {self._base_key(f, a, b) for f in fat_order for a in ass_order for b in breast_order}

        created = existing = removed = 0
        # Remove only obsolete derived BASE categories. Custom presets are never touched here.
        obsolete = db.execute(select(BodyProportionPreset).where(
            BodyProportionPreset.sex == sex,
            BodyProportionPreset.is_base_category.is_(True),
        )).scalars().all()
        for row in obsolete:
            if row.base_category_key and row.base_category_key not in expected:
                self._delete_preset_row(db, row)
                removed += 1

        order = 100.0
        for fat_band in fat_order:
            for ass_band in ass_order:
                for breast_band in breast_order:
                    base_key = self._base_key(fat_band, ass_band, breast_band)
                    name = self._base_name(config, fat_band, ass_band, breast_band)
                    slug = self._slug(name)
                    found = db.execute(select(BodyProportionPreset).where(
                        BodyProportionPreset.sex == sex,
                        BodyProportionPreset.base_category_key == base_key,
                        BodyProportionPreset.is_base_category.is_(True),
                    )).scalar_one_or_none()
                    if found is None:
                        found = db.execute(select(BodyProportionPreset).where(
                            BodyProportionPreset.sex == sex,
                            (BodyProportionPreset.display_name == name) | (BodyProportionPreset.category_slug == slug),
                        )).scalar_one_or_none()
                    if found:
                        found.fat_band = fat_band
                        found.ass_band = ass_band
                        found.breast_band = breast_band
                        found.is_base_category = True
                        found.base_category_key = base_key
                        found.sort_order = order
                        db.add(found)
                        db.commit()
                        existing += 1
                        order += 100.0
                        continue
                    values = self._base_values(config, fat_band, ass_band, breast_band)
                    key, _ = self._next_identity(db, sex)
                    row = BodyProportionPreset(
                        sex=sex, sort_order=order, profile_key=key, display_name=name,
                        category_slug=self._slug(name), fat_band=fat_band, ass_band=ass_band,
                        breast_band=breast_band, is_base_category=True, base_category_key=base_key,
                        **values,
                    )
                    db.add(row)
                    db.commit()
                    created += 1
                    order += 100.0
        result = {"created": created, "existing": existing, "removed": removed, "total_base": len(expected)}
        try:
            from app.services.bubble_butt_tool_service import bubble_butt_tool_service
            bubble_butt_tool_service.sync_matrix(db, sex)
        except Exception:
            # Bubble Butt is a dependent stage. Body matrix synchronization must remain
            # authoritative and must never be rolled back by an optional second stage.
            pass
        return result

    def ensure_defaults(self, db: Session, sex: str) -> None:
        sex = self._validate_sex(sex)
        if sex != "woman":
            return
        config = self.get_config(db, sex)
        fat_order, ass_order, breast_order = self._formula_orders(config["formula"])
        expected_count = len(fat_order) * len(ass_order) * len(breast_order)
        count = db.execute(select(func.count()).select_from(BodyProportionPreset).where(
            BodyProportionPreset.sex == sex, BodyProportionPreset.is_base_category.is_(True)
        )).scalar_one()
        if int(count or 0) != expected_count:
            self.seed_defaults(db, sex)

    def recalculate_defaults(self, db: Session, sex: str, include_ready: bool = False) -> dict:
        sex = self._validate_sex(sex)
        config = self.get_config(db, sex)
        rows = db.execute(select(BodyProportionPreset).where(
            BodyProportionPreset.sex == sex, BodyProportionPreset.is_base_category.is_(True)
        )).scalars().all()
        updated = skipped = 0
        for row in rows:
            if row.status == "ready" and not include_ready:
                skipped += 1; continue
            if not row.fat_band or not row.ass_band or not row.breast_band:
                continue
            values = self._base_values(config, row.fat_band, row.ass_band, row.breast_band)
            for k, v in values.items(): setattr(row, k, v)
            row.display_name = self._base_name(config, row.fat_band, row.ass_band, row.breast_band)
            row.category_slug = self._slug(row.display_name)
            row.status = "draft"
            db.add(row); updated += 1
        db.commit()
        return {"updated": updated, "skipped_ready": skipped}

    def synchronize_preset_with_rules(self, db: Session, preset_id: int) -> BodyProportionPreset:
        """Forget this preset's saved body values and re-derive them from current global rules.

        This operation is intentionally scoped to one Body Proportion base preset.
        It preserves the existing preview/storage reference, but marks the preset as draft
        because the stored image may no longer match the newly synchronized values.
        """
        row = self.get_preset(db, preset_id)
        if not row.is_base_category or not row.fat_band or not row.ass_band or not row.breast_band:
            raise ValueError("Only derived base body-proportion categories can be synchronized with global rules.")

        config = self.get_config(db, row.sex)
        values = self._base_values(config, row.fat_band, row.ass_band, row.breast_band)

        for field, value in values.items():
            setattr(row, field, value)

        row.display_name = self._base_name(config, row.fat_band, row.ass_band, row.breast_band)
        row.category_slug = self._slug(row.display_name)
        row.status = "draft"
        row.last_error = None

        db.add(row)
        db.commit()
        db.refresh(row)
        return row


    def synchronize_all_base_presets(self, db: Session) -> list[BodyProportionPreset]:
        """Re-derive every base category from the current global rules.

        Custom/intermediate presets are intentionally excluded. Each base preset
        uses the exact same synchronization path as the existing per-card action.
        """
        preset_ids = db.scalars(
            select(BodyProportionPreset.id).where(
                BodyProportionPreset.is_base_category.is_(True)
            )
        ).all()

        restored: list[BodyProportionPreset] = []
        for preset_id in preset_ids:
            restored.append(self.synchronize_preset_with_rules(db, int(preset_id)))
        return restored


    def create_preset(self, db: Session, data) -> BodyProportionPreset:
        sex = self._validate_sex(data.sex)
        config = self.get_config(db, sex); fixed = config["fixed_values"]
        values = {
            "hips_size": data.hips_size, "fat_thin": data.fat_thin, "breasts_size": data.breasts_size,
            "skin_tone": fixed.get("skin_tone", 0.0) if data.skin_tone is None else data.skin_tone,
            "hair_length": fixed.get("hair_length", 0.0) if data.hair_length is None else data.hair_length,
        }
        self._assert_limits(config, values)
        key, fallback_slug = self._next_identity(db, sex)
        name = (data.display_name or key).strip()
        slug = self._slug(name) if data.display_name else fallback_slug
        # Avoid collisions for custom/intermediate rows.
        original_slug = slug; suffix = 2
        while db.execute(select(BodyProportionPreset.id).where(BodyProportionPreset.sex == sex, BodyProportionPreset.category_slug == slug)).scalar_one_or_none():
            slug = f"{original_slug}_{suffix}"; suffix += 1
        row = BodyProportionPreset(
            sex=sex, sort_order=data.sort_order if data.sort_order is not None else self._next_sort_order(db, sex),
            profile_key=key, display_name=name, category_slug=slug,
            fat_band=getattr(data, "fat_band", None), ass_band=getattr(data, "ass_band", None),
            breast_band=getattr(data, "breast_band", None), is_base_category=bool(getattr(data, "is_base_category", False)),
            base_category_key=getattr(data, "base_category_key", None), **values,
        )
        db.add(row); db.commit(); db.refresh(row); return row

    def list_presets(self, db: Session, sex: str) -> list[BodyProportionPreset]:
        sex = self._validate_sex(sex)
        return list(db.execute(select(BodyProportionPreset).where(BodyProportionPreset.sex == sex).order_by(BodyProportionPreset.sort_order.asc(), BodyProportionPreset.id.asc())).scalars().all())

    def get_preset(self, db: Session, preset_id: int) -> BodyProportionPreset:
        row = db.get(BodyProportionPreset, preset_id)
        if not row: raise LookupError("Body proportion preset not found.")
        return row

    def update_preset(self, db: Session, preset_id: int, data) -> BodyProportionPreset:
        row = self.get_preset(db, preset_id); patch = data.model_dump(exclude_unset=True)
        values = {k: patch.get(k, getattr(row, k)) for k in ("hips_size", "fat_thin", "breasts_size", "skin_tone", "hair_length")}
        self._assert_limits(self.get_config(db, row.sex), values)
        for field, value in patch.items(): setattr(row, field, value)
        if any(field in patch for field in values): row.status = "draft"
        db.add(row); db.commit(); db.refresh(row); return row

    def create_next(self, db: Session, preset_id: int, display_name: str | None = None) -> BodyProportionPreset:
        current = self.get_preset(db, preset_id)
        # Generic extension: continue from the closest delta between current and previous row.
        previous = db.execute(select(BodyProportionPreset).where(
            BodyProportionPreset.sex == current.sex, BodyProportionPreset.sort_order < current.sort_order
        ).order_by(BodyProportionPreset.sort_order.desc()).limit(1)).scalar_one_or_none()
        if previous:
            dh = current.hips_size - previous.hips_size; df = current.fat_thin - previous.fat_thin; dbs = current.breasts_size - previous.breasts_size
        else:
            dh, df, dbs = 0.25, 0.0, 0.1
        created = type("PresetInput", (), {
            "sex": current.sex, "sort_order": current.sort_order + 50.0,
            "display_name": display_name or f"Custom after {current.profile_key}",
            "hips_size": current.hips_size + dh, "fat_thin": current.fat_thin + df,
            "breasts_size": current.breasts_size + dbs, "skin_tone": current.skin_tone,
            "hair_length": current.hair_length, "fat_band": None, "ass_band": None, "breast_band": None,
            "is_base_category": False, "base_category_key": None,
        })()
        return self.create_preset(db, created)

    def interpolate(self, db: Session, data) -> BodyProportionPreset:
        before, after = self.get_preset(db, data.before_id), self.get_preset(db, data.after_id)
        if before.sex != after.sex: raise ValueError("Cannot interpolate presets from different sexes.")
        ratio = float(data.ratio)
        def mix(a, b): return float(a) + (float(b) - float(a)) * ratio
        created = type("PresetInput", (), {
            "sex": before.sex, "sort_order": mix(before.sort_order, after.sort_order),
            "display_name": data.display_name or f"Intermediate {before.profile_key} / {after.profile_key} ({ratio:.0%})",
            "hips_size": mix(before.hips_size, after.hips_size), "fat_thin": mix(before.fat_thin, after.fat_thin),
            "breasts_size": mix(before.breasts_size, after.breasts_size), "skin_tone": mix(before.skin_tone, after.skin_tone),
            "hair_length": mix(before.hair_length, after.hair_length), "fat_band": None, "ass_band": None,
            "breast_band": None, "is_base_category": False, "base_category_key": None,
        })()
        return self.create_preset(db, created)

    def _delete_preset_row(self, db: Session, row: BodyProportionPreset) -> bool:
        storage_deleted = False
        if row.image_storage_file_id:
            stored = db.get(StorageFile, row.image_storage_file_id)
            if stored:
                try:
                    storage_service.delete_file(db, storage_file=stored)
                    storage_deleted = True
                finally:
                    db.delete(stored)
        if row.local_mirror_path:
            mirror = Path(row.local_mirror_path)
            if mirror.exists():
                import shutil
                shutil.rmtree(mirror, ignore_errors=True)
        db.delete(row)
        db.commit()
        return storage_deleted

    def delete_preset(self, db: Session, preset_id: int) -> None:
        row = self.get_preset(db, preset_id)
        self._delete_preset_row(db, row)

    def reset_tool(
        self,
        db: Session,
        sex: str,
        *,
        delete_workflow_mappings: bool = False,
    ) -> dict:
        sex = self._validate_sex(sex)
        rows = list(db.execute(select(BodyProportionPreset).where(
            BodyProportionPreset.sex == sex
        )).scalars().all())
        deleted_storage = 0
        for row in rows:
            if self._delete_preset_row(db, row):
                deleted_storage += 1

        config_row = db.execute(select(BodyProportionWorkflowConfig).where(
            BodyProportionWorkflowConfig.sex == sex
        )).scalar_one_or_none()

        deleted_config = False
        if config_row:
            if delete_workflow_mappings:
                db.delete(config_row)
                deleted_config = True
            else:
                # Reset only this tool's generated data/rules while preserving the
                # already configured ComfyUI workflow and explicit node mappings.
                config_row.limits_json = deepcopy(DEFAULT_LIMITS)
                config_row.formula_json = deepcopy(DEFAULT_FORMULA)
                config_row.fixed_values_json = deepcopy(DEFAULT_FIXED_VALUES)
                config_row.storage_mode = "auto"
                config_row.notes = None
            db.commit()

        root = Path(str(getattr(settings, "LOCAL_STORAGE_DIR", "storage"))) / "body-proportions-library" / f"proportions_{sex}"
        mirror_removed = root.exists()
        if mirror_removed:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        bubble_reset = {"deleted_presets": 0, "deleted_config": False}
        try:
            from app.services.bubble_butt_tool_service import bubble_butt_tool_service
            bubble_reset = bubble_butt_tool_service.reset(
                db, sex, delete_workflow_mappings=delete_workflow_mappings
            )
        except Exception:
            db.rollback()
        return {
            "sex": sex,
            "deleted_presets": len(rows),
            "deleted_storage_files": deleted_storage,
            "deleted_config": deleted_config,
            "mirror_removed": mirror_removed,
            "bubble_butt_deleted_presets": bubble_reset["deleted_presets"],
            "bubble_butt_deleted_config": bubble_reset["deleted_config"],
        }

    @staticmethod
    def _workflow_differences(before, after, path=()):
        differences = []
        if isinstance(before, dict) and isinstance(after, dict):
            before_keys = set(before.keys())
            after_keys = set(after.keys())
            for key in sorted(before_keys | after_keys, key=str):
                current = path + (str(key),)
                if key not in before:
                    differences.append((current, "added"))
                elif key not in after:
                    differences.append((current, "removed"))
                else:
                    differences.extend(BodyProportionToolService._workflow_differences(before[key], after[key], current))
            return differences
        if isinstance(before, list) and isinstance(after, list):
            if before != after:
                differences.append((path, "changed"))
            return differences
        if before != after:
            differences.append((path, "changed"))
        return differences

    @staticmethod
    def _workflow_sha256(workflow: dict) -> str:
        payload = json.dumps(
            workflow,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _validate_original_workflow_required_inputs(workflow: dict) -> None:
        """Validate only; never infer, create, or repair workflow connections."""
        if not isinstance(workflow, dict):
            raise ValueError("Configured ComfyUI workflow must be a JSON object.")

        required_by_class = {
            "KSampler": ("model", "positive", "negative", "latent_image"),
            "VAEDecode": ("samples", "vae"),
        }
        missing: list[str] = []

        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type") or "")
            required = required_by_class.get(class_type)
            if not required:
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                inputs = {}
            for input_name in required:
                if input_name not in inputs:
                    missing.append(f"{node_id}.{input_name} ({class_type})")

        if missing:
            digest = BodyProportionToolService._workflow_sha256(workflow)
            raise ValueError(
                "The ORIGINAL ComfyUI API workflow saved in Body Proportions is incomplete "
                "before any mapped value is changed. Missing required inputs: "
                + ", ".join(missing)
                + f". Original workflow SHA256: {digest}. "
                "The Body Proportion Tool did not remove these inputs and will not infer or repair them. "
                "Export/load a complete ComfyUI API workflow, then save the configuration again."
            )

    def _patch_workflow(self, workflow: dict, mapping: dict, values: dict) -> dict:
        if not isinstance(workflow, dict):
            raise ValueError("Configured ComfyUI workflow must be a JSON object.")

        original = deepcopy(workflow)
        result = deepcopy(workflow)
        allowed_paths = set()

        for key in self.PATCH_KEYS:
            target = mapping.get(key)
            if not target:
                continue
            node_id = str(target.get("node_id", "")).strip()
            input_name = str(target.get("input_name", "")).strip()
            if not node_id or not input_name:
                continue
            if node_id not in result:
                raise ValueError(f"Mapped ComfyUI node {node_id} for {key} does not exist.")
            node = result[node_id]
            if not isinstance(node, dict):
                raise ValueError(f"Mapped ComfyUI node {node_id} for {key} is invalid.")
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                raise ValueError(f"Mapped ComfyUI node {node_id} has no inputs object.")
            if input_name not in inputs:
                raise ValueError(
                    f"Mapped input {input_name!r} does not exist on ComfyUI node {node_id} for {key}. "
                    "The body proportion tool will not create or infer missing workflow inputs."
                )
            inputs[input_name] = deepcopy(values[key])
            allowed_paths.add((node_id, "inputs", input_name))

        unexpected = []
        for diff_path, diff_kind in self._workflow_differences(original, result):
            if diff_path not in allowed_paths:
                unexpected.append((diff_path, diff_kind))

        if unexpected:
            preview = ", ".join(".".join(path) for path, _ in unexpected[:10])
            raise RuntimeError(
                "Body proportion workflow integrity check failed. "
                "Only explicitly mapped node inputs may change. Unexpected changes: " + preview
            )

        return result

    def _category_parts(self, preset: BodyProportionPreset) -> list[str]:
        if preset.is_base_category and preset.fat_band:
            return [preset.fat_band, preset.category_slug]
        return ["custom", preset.category_slug]

    def _mirror_dir(self, preset: BodyProportionPreset) -> Path:
        root = Path(str(getattr(settings, "LOCAL_STORAGE_DIR", "storage"))) / "body-proportions-library"
        return root / f"proportions_{preset.sex}" / Path(*self._category_parts(preset))

    def _write_mirror(self, preset: BodyProportionPreset, content: bytes, content_type: str | None) -> str:
        directory = self._mirror_dir(preset); directory.mkdir(parents=True, exist_ok=True)
        suffix = ".png" if not content_type or "png" in content_type else ".jpg"
        image_path = directory / f"preview{suffix}"
        for existing in directory.glob("preview.*"):
            if existing != image_path: existing.unlink(missing_ok=True)
        image_path.write_bytes(content)
        values = {
            "profile_key": preset.profile_key, "display_name": preset.display_name, "sex": preset.sex,
            "fat_band": preset.fat_band, "ass_band": preset.ass_band, "breast_band": preset.breast_band,
            "hips_size": preset.hips_size, "fat_thin": preset.fat_thin, "breasts_size": preset.breasts_size,
            "skin_tone": preset.skin_tone, "hair_length": preset.hair_length,
        }
        (directory / "values.json").write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / "values.txt").write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")
        return str(directory)

    def _resolved_storage_provider(self, db: Session, mode: str) -> str:
        if mode == "auto": return storage_service.active_provider(db)
        return {"local": StorageProvider.LOCAL.value, "amazon_s3": StorageProvider.AMAZON_S3.value,
                "cloudflare_r2": StorageProvider.CLOUDFLARE_R2.value}[mode]

    def _save_selected(self, db: Session, *, mode: str, content: bytes, filename: str, content_type: str, folder: str) -> StorageFile:
        provider = self._resolved_storage_provider(db, mode)
        if provider == StorageProvider.LOCAL.value:
            return storage_service._save_local(db, user_id=None, content=content, original_filename=filename, content_type=content_type, folder=folder)
        return storage_service._save_remote(db, provider=provider, user_id=None, content=content, original_filename=filename, content_type=content_type, folder=folder)

    def storage_options(self, db: Session) -> dict:
        return {"active_provider": storage_service.active_provider(db), "modes": ["auto", "local", "amazon_s3", "cloudflare_r2"]}


    @staticmethod
    def _portable_preview_name(stored: StorageFile) -> str:
        content_type = str(stored.content_type or "").lower()
        original = str(stored.original_filename or "").lower()
        if "webp" in content_type or original.endswith(".webp"):
            return "preview.webp"
        if "jpeg" in content_type or original.endswith((".jpg", ".jpeg")):
            return "preview.jpg"
        return "preview.png"

    def _preview_storage_map(self, db: Session, preset: BodyProportionPreset) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for provider, raw_id in (getattr(preset, "preview_storage_json", {}) or {}).items():
            try:
                storage_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if db.get(StorageFile, storage_id):
                mapping[str(provider)] = storage_id

        # Backward compatibility: existing rows only know image_storage_file_id.
        if preset.image_storage_file_id:
            stored = db.get(StorageFile, preset.image_storage_file_id)
            if stored:
                mapping.setdefault(storage_service.provider_for_file(stored), stored.id)
        return mapping

    def _source_provider(self, db: Session, source: str) -> str:
        source = self._validate_storage_mode(source)
        return self._resolved_storage_provider(db, source)

    def active_preview_source(self, db: Session, sex: str) -> str:
        sex = self._validate_sex(sex)
        row = db.execute(
            select(BodyProportionWorkflowConfig).where(BodyProportionWorkflowConfig.sex == sex)
        ).scalar_one_or_none()
        return self._validate_storage_mode(getattr(row, "active_preview_source", "auto") if row else "auto")

    def preview_storage_file(
        self,
        db: Session,
        preset: BodyProportionPreset,
        *,
        source: str | None = None,
    ) -> StorageFile | None:
        selected_source = source or self.active_preview_source(db, preset.sex)
        provider = self._source_provider(db, selected_source)
        mapping = self._preview_storage_map(db, preset)
        storage_id = mapping.get(provider)
        if storage_id:
            return db.get(StorageFile, storage_id)

        # Legacy-safe fallback only when no multi-source map exists yet.
        if not getattr(preset, "preview_storage_json", None) and preset.image_storage_file_id:
            return db.get(StorageFile, preset.image_storage_file_id)
        return None

    def _persist_storage_copy(
        self,
        db: Session,
        preset: BodyProportionPreset,
        stored: StorageFile,
    ) -> None:
        mapping = self._preview_storage_map(db, preset)
        mapping[storage_service.provider_for_file(stored)] = stored.id
        preset.preview_storage_json = mapping
        if not preset.image_storage_file_id:
            preset.image_storage_file_id = stored.id
        db.add(preset)
        db.commit()
        db.refresh(preset)

    def _required_library_rows(self, db: Session, sex: str) -> list[BodyProportionPreset]:
        return list(db.execute(
            select(BodyProportionPreset).where(
                BodyProportionPreset.sex == sex,
                BodyProportionPreset.status == "ready",
            ).order_by(BodyProportionPreset.sort_order.asc(), BodyProportionPreset.id.asc())
        ).scalars().all())

    def verify_preview_source(self, db: Session, sex: str, source: str) -> dict[str, Any]:
        sex = self._validate_sex(sex)
        provider = self._source_provider(db, source)
        rows = self._required_library_rows(db, sex)

        checked = 0
        missing: list[dict[str, Any]] = []
        for preset in rows:
            stored = self.preview_storage_file(db, preset, source=source)
            if not stored or storage_service.provider_for_file(stored) != provider:
                missing.append({"preset_id": preset.id, "profile_key": preset.profile_key, "reason": "missing"})
                continue
            try:
                # Explicit verification is allowed to read the object. This proves that the
                # DB record is not stale and that credentials/path are actually usable.
                content = storage_service.read_bytes(db, storage_file=stored)
                if not content:
                    raise ValueError("empty file")
                checked += 1
            except Exception as error:
                missing.append({
                    "preset_id": preset.id,
                    "profile_key": preset.profile_key,
                    "reason": str(error),
                })

        from app.services.bubble_butt_tool_service import bubble_butt_tool_service
        bubble = bubble_butt_tool_service.verify_source(db, sex, source)
        bubble_missing = [
            {"stage": "bubble_butt", **item} for item in bubble["missing"]
        ]
        total_required = len(rows) + int(bubble["required"])
        total_verified = checked + int(bubble["verified"])
        all_missing = missing + bubble_missing
        return {
            "sex": sex,
            "source": source,
            "provider": provider,
            "required": total_required,
            "verified": total_verified,
            "missing_count": len(all_missing),
            "complete": total_required > 0 and not all_missing,
            "missing": all_missing,
        }

    def library_status(self, db: Session, sex: str) -> dict[str, Any]:
        sex = self._validate_sex(sex)
        rows = self._required_library_rows(db, sex)
        sources = {}
        for source in ("local", "cloudflare_r2", "amazon_s3"):
            provider = self._source_provider(db, source)
            available = 0
            for preset in rows:
                stored = self.preview_storage_file(db, preset, source=source)
                if stored and storage_service.provider_for_file(stored) == provider:
                    available += 1
            from app.services.bubble_butt_tool_service import bubble_butt_tool_service
            bubble_rows = bubble_butt_tool_service.ready_rows(db, sex)
            bubble_available = sum(
                1 for bubble_row in bubble_rows
                if (
                    (bubble_file := bubble_butt_tool_service.preview_storage_file(db, bubble_row, source=source))
                    and storage_service.provider_for_file(bubble_file) == provider
                )
            )
            total_required = len(rows) + len(bubble_rows)
            total_available = available + bubble_available
            sources[source] = {
                "provider": provider,
                "available": total_available,
                "required": total_required,
                "complete_by_records": total_required > 0 and total_available == total_required,
                "body_available": available,
                "bubble_butt_available": bubble_available,
            }

        active_source = self.active_preview_source(db, sex)
        return {
            "sex": sex,
            "active_source": active_source,
            "active_provider": self._source_provider(db, active_source),
            "required": len(rows),
            "sources": sources,
        }

    def copy_preview_library(
        self,
        db: Session,
        sex: str,
        source: str,
        target: str,
    ) -> dict[str, Any]:
        sex = self._validate_sex(sex)
        source_provider = self._source_provider(db, source)
        target_provider = self._source_provider(db, target)
        if source_provider == target_provider:
            raise ValueError("Source and target resolve to the same storage provider.")

        rows = self._required_library_rows(db, sex)
        copied = 0
        skipped_existing = 0
        failed: list[dict[str, Any]] = []

        for preset in rows:
            try:
                source_file = self.preview_storage_file(db, preset, source=source)
                if not source_file or storage_service.provider_for_file(source_file) != source_provider:
                    raise ValueError("Source preview is not available.")

                existing_target = self.preview_storage_file(db, preset, source=target)
                if existing_target and storage_service.provider_for_file(existing_target) == target_provider:
                    try:
                        if storage_service.read_bytes(db, storage_file=existing_target):
                            skipped_existing += 1
                            continue
                    except Exception:
                        pass

                content = storage_service.read_bytes(db, storage_file=source_file)
                content_type = source_file.content_type or "image/png"
                folder = "/".join([
                    "body-proportion-library",
                    f"proportions_{preset.sex}",
                    *self._category_parts(preset),
                ])
                stored = self._save_selected(
                    db,
                    mode=target,
                    content=content,
                    filename=self._portable_preview_name(source_file),
                    content_type=content_type,
                    folder=folder,
                )
                self._persist_storage_copy(db, preset, stored)
                copied += 1
            except Exception as error:
                db.rollback()
                failed.append({
                    "preset_id": preset.id,
                    "profile_key": preset.profile_key,
                    "error": str(error),
                })

        from app.services.bubble_butt_tool_service import bubble_butt_tool_service
        bubble_copy = bubble_butt_tool_service.copy_ready(db, sex, source, target)

        # The configuration travels with every provider-to-provider transfer.
        manifest = self.configuration_manifest(db, sex)
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        self._save_selected(
            db, mode=target, content=manifest_bytes, filename="configuration.json",
            content_type="application/json",
            folder=f"body-proportion-library/proportions_{sex}",
        )
        self.write_configuration_manifest(db, sex)

        verification = self.verify_preview_source(db, sex, target)
        return {
            "sex": sex,
            "source": source,
            "source_provider": source_provider,
            "target": target,
            "target_provider": target_provider,
            "copied": copied + bubble_copy["copied"],
            "skipped_existing": skipped_existing + bubble_copy["skipped"],
            "failed": failed,
            "bubble_butt_failed": bubble_copy["failed"],
            "configuration_copied": True,
            "verification": verification,
        }

    def activate_preview_source(self, db: Session, sex: str, source: str) -> dict[str, Any]:
        sex = self._validate_sex(sex)
        source = self._validate_storage_mode(source)
        verification = self.verify_preview_source(db, sex, source)
        if not verification["complete"]:
            raise ValueError(
                f"Cannot activate {source}: {verification['missing_count']} required previews are missing or unreadable."
            )

        row = db.execute(
            select(BodyProportionWorkflowConfig).where(BodyProportionWorkflowConfig.sex == sex)
        ).scalar_one_or_none()
        if row is None:
            row = BodyProportionWorkflowConfig(
                sex=sex,
                workflow_json=None,
                input_mapping_json={},
                limits_json=deepcopy(DEFAULT_LIMITS),
                formula_json=deepcopy(DEFAULT_FORMULA),
                fixed_values_json=deepcopy(DEFAULT_FIXED_VALUES),
                storage_mode="auto",
                active_preview_source=source,
                is_enabled=False,
            )
            db.add(row)
        else:
            row.active_preview_source = source
            db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "sex": sex,
            "active_source": source,
            "active_provider": self._source_provider(db, source),
            "verification": verification,
        }

    def build_portable_zip(self, db: Session, sex: str, source: str) -> bytes:
        sex = self._validate_sex(sex)
        verification = self.verify_preview_source(db, sex, source)
        if not verification["complete"]:
            raise ValueError(
                f"ZIP export requires a complete source. Missing: {verification['missing_count']}."
            )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest = self.configuration_manifest(db, sex)
            archive.writestr(
                f"proportions_{sex}/configuration.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            for preset in self._required_library_rows(db, sex):
                stored = self.preview_storage_file(db, preset, source=source)
                if not stored:
                    continue
                content = storage_service.read_bytes(db, storage_file=stored)
                folder = "/".join([
                    f"proportions_{preset.sex}",
                    *self._category_parts(preset),
                ])
                metadata = {
                    "format_version": 2,
                    "profile_key": preset.profile_key,
                    "display_name": preset.display_name,
                    "category_slug": preset.category_slug,
                    "sex": preset.sex,
                    "sort_order": preset.sort_order,
                    "fat_band": preset.fat_band,
                    "ass_band": preset.ass_band,
                    "breast_band": preset.breast_band,
                    "is_base_category": bool(preset.is_base_category),
                    "base_category_key": preset.base_category_key,
                    "hips_size": preset.hips_size,
                    "fat_thin": preset.fat_thin,
                    "breasts_size": preset.breasts_size,
                    "skin_tone": preset.skin_tone,
                    "hair_length": preset.hair_length,
                }
                archive.writestr(f"{folder}/{self._portable_preview_name(stored)}", content)
                archive.writestr(
                    f"{folder}/values.json",
                    json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
                )
                archive.writestr(
                    f"{folder}/values.txt",
                    "\n".join(f"{key}={value}" for key, value in metadata.items()).encode("utf-8"),
                )
            from app.services.bubble_butt_tool_service import bubble_butt_tool_service
            bubble_butt_tool_service.add_to_zip(archive, db, sex, source)
        return buffer.getvalue()

    @staticmethod
    def _safe_zip_path(filename: str) -> PurePosixPath:
        normalized = str(filename or "").replace("\\", "/").lstrip("/")
        path = PurePosixPath(normalized)
        if not normalized or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"Unsafe ZIP path: {filename}")
        return path

    @staticmethod
    def _portable_sex_root(path: PurePosixPath) -> tuple[str, int]:
        for index, part in enumerate(path.parts):
            if part == "proportions_woman":
                return "woman", index
            if part == "proportions_man":
                return "man", index
        raise ValueError("Path is outside proportions_woman/proportions_man.")

    def import_portable_zip(self, db: Session, file_obj, target: str) -> dict[str, Any]:
        target = self._validate_storage_mode(target)
        imported = 0
        created = 0
        updated = 0
        skipped = 0
        sexes: set[str] = set()
        errors: list[dict[str, str]] = []

        try:
            archive = zipfile.ZipFile(file_obj)
        except zipfile.BadZipFile as error:
            raise ValueError("The imported file is not a valid ZIP.") from error

        with archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            if len(files) > 10000:
                raise ValueError("ZIP contains more than 10,000 files.")
            if sum(max(0, int(info.file_size)) for info in files) > 2 * 1024 * 1024 * 1024:
                raise ValueError("ZIP uncompressed content exceeds 2 GB.")

            safe_paths = {info.filename: self._safe_zip_path(info.filename) for info in files}
            configuration_files = [
                info for info in files
                if safe_paths[info.filename].name.lower() == "configuration.json"
                and any(part in {"proportions_woman", "proportions_man"} for part in safe_paths[info.filename].parts)
            ]
            for config_info in configuration_files:
                manifest = json.loads(archive.read(config_info).decode("utf-8"))
                self._apply_configuration_manifest(db, manifest, target=target)
                manifest_sex = str(manifest.get("sex") or "").strip().lower()
                if manifest_sex in self.SEXES:
                    sexes.add(manifest_sex)

            metadata_files = [
                info for info in files
                if safe_paths[info.filename].name.lower() == "values.json"
                and "bubble_butt" not in safe_paths[info.filename].parts
            ]
            if not metadata_files:
                raise ValueError("ZIP has no Body Proportions values.json files.")

            for metadata_info in metadata_files:
                metadata_path = safe_paths[metadata_info.filename]
                try:
                    sex, root_index = self._portable_sex_root(metadata_path)
                    sexes.add(sex)
                    relative_dir = PurePosixPath(*metadata_path.parts[root_index + 1:-1])
                    if not relative_dir.parts:
                        raise ValueError("Invalid category path.")

                    metadata = json.loads(archive.read(metadata_info).decode("utf-8"))
                    if str(metadata.get("sex") or sex).strip().lower() != sex:
                        raise ValueError("Metadata sex does not match proportions_* folder.")

                    preview_info = next((
                        info for info in files
                        if safe_paths[info.filename].parent == metadata_path.parent
                        and safe_paths[info.filename].name.lower()
                        in {"preview.png", "preview.jpg", "preview.jpeg", "preview.webp"}
                    ), None)
                    if preview_info is None:
                        skipped += 1
                        continue

                    preview_path = safe_paths[preview_info.filename]
                    image = archive.read(preview_info)
                    if not image:
                        raise ValueError("Preview image is empty.")

                    profile_key = str(metadata.get("profile_key") or "").strip()
                    category_slug = str(metadata.get("category_slug") or metadata_path.parent.name).strip()
                    display_name = str(metadata.get("display_name") or category_slug).strip()
                    if not profile_key:
                        profile_key = f"import_{self._slug(category_slug)}"

                    row = db.execute(select(BodyProportionPreset).where(
                        BodyProportionPreset.sex == sex,
                        BodyProportionPreset.profile_key == profile_key,
                    )).scalar_one_or_none()
                    if row is None:
                        row = db.execute(select(BodyProportionPreset).where(
                            BodyProportionPreset.sex == sex,
                            BodyProportionPreset.category_slug == category_slug,
                        )).scalar_one_or_none()

                    values = {
                        "hips_size": float(metadata["hips_size"]),
                        "fat_thin": float(metadata["fat_thin"]),
                        "breasts_size": float(metadata["breasts_size"]),
                        "skin_tone": float(metadata.get("skin_tone", DEFAULT_FIXED_VALUES["skin_tone"])),
                        "hair_length": float(metadata.get("hair_length", DEFAULT_FIXED_VALUES["hair_length"])),
                    }

                    if row is None:
                        row = BodyProportionPreset(
                            sex=sex,
                            sort_order=float(metadata.get("sort_order") or self._next_sort_order(db, sex)),
                            profile_key=profile_key,
                            display_name=display_name,
                            category_slug=category_slug,
                            fat_band=metadata.get("fat_band"),
                            ass_band=metadata.get("ass_band"),
                            breast_band=metadata.get("breast_band"),
                            is_base_category=bool(metadata.get("is_base_category", False)),
                            base_category_key=metadata.get("base_category_key"),
                            preview_storage_json={},
                            **values,
                        )
                        db.add(row)
                        db.flush()
                        created += 1
                    else:
                        row.display_name = display_name
                        row.sort_order = float(metadata.get("sort_order") or row.sort_order)
                        row.fat_band = metadata.get("fat_band")
                        row.ass_band = metadata.get("ass_band")
                        row.breast_band = metadata.get("breast_band")
                        row.is_base_category = bool(metadata.get("is_base_category", row.is_base_category))
                        row.base_category_key = metadata.get("base_category_key")
                        for key, value in values.items():
                            setattr(row, key, value)
                        updated += 1

                    content_type = mimetypes.guess_type(preview_path.name.lower())[0] or "image/png"
                    folder = "/".join([
                        "body-proportion-library",
                        f"proportions_{sex}",
                        *relative_dir.parts,
                    ])
                    stored = self._save_selected(
                        db,
                        mode=target,
                        content=image,
                        filename=preview_path.name.lower(),
                        content_type=content_type,
                        folder=folder,
                    )
                    self._persist_storage_copy(db, row, stored)

                    row.local_mirror_path = self._write_mirror(row, image, content_type)
                    row.status = "ready"
                    row.last_error = None
                    row.generated_at = utc_now()
                    row.generation_metadata_json = {
                        **(row.generation_metadata_json or {}),
                        "portable_import": True,
                        "portable_path": f"proportions_{sex}/{relative_dir.as_posix()}",
                        "import_target": target,
                        "storage_provider": stored.provider,
                    }
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    imported += 1
                except Exception as error:
                    db.rollback()
                    errors.append({"path": metadata_info.filename, "error": str(error)})

            from app.services.bubble_butt_tool_service import bubble_butt_tool_service
            bubble_result = bubble_butt_tool_service.import_from_archive(
                archive, files, safe_paths, target
            )
            imported += bubble_result["imported"]
            created += bubble_result["created"]
            updated += bubble_result["updated"]
            errors.extend(bubble_result["errors"])
            sexes.update(
                str(json.loads(archive.read(info)).get("sex"))
                for info in metadata_files
                if safe_paths[info.filename].name.lower() == "values.json"
            )

        for imported_sex in list(sexes):
            if imported_sex in self.SEXES:
                self.seed_defaults(db, imported_sex)
                from app.services.bubble_butt_tool_service import bubble_butt_tool_service
                bubble_butt_tool_service.sync_matrix(db, imported_sex)
                self.write_configuration_manifest(db, imported_sex)

        verifications = {}
        for imported_sex in sexes:
            verifications[imported_sex] = self.verify_preview_source(db, imported_sex, target)

        return {
            "imported": imported,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "sexes": sorted(sexes),
            "target": target,
            "errors": errors,
            "verifications": verifications,
        }



    def configuration_manifest(self, db: Session, sex: str) -> dict[str, Any]:
        from app.services.bubble_butt_tool_service import bubble_butt_tool_service
        body = self.get_config(db, sex)
        bubble = bubble_butt_tool_service.get_config(db, sex)
        return {
            "format_version": 1,
            "tool": "body_proportions",
            "sex": sex,
            "body": {
                "workflow": body["workflow"],
                "input_mapping": body["input_mapping"],
                "limits": body["limits"],
                "formula": body["formula"],
                "fixed_values": body["fixed_values"],
                "is_enabled": body["is_enabled"],
                "notes": body["notes"],
                "source_storage_mode": body["storage_mode"],
                "source_active_preview_source": body["active_preview_source"],
            },
            "bubble_butt": {
                "workflow": bubble["workflow"],
                "input_mapping": bubble["input_mapping"],
                "bubble_values": bubble["bubble_values"],
                "is_enabled": bubble["is_enabled"],
                "notes": bubble["notes"],
            },
        }

    def write_configuration_manifest(self, db: Session, sex: str) -> str:
        manifest = self.configuration_manifest(db, sex)
        root = Path(str(getattr(settings, "LOCAL_STORAGE_DIR", "storage"))) / "body-proportions-library" / f"proportions_{sex}"
        root.mkdir(parents=True, exist_ok=True)
        path = root / "configuration.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def _apply_configuration_manifest(self, db: Session, manifest: dict[str, Any], *, target: str) -> None:
        from app.models.body_proportion_tool import BubbleButtWorkflowConfig
        from app.services.bubble_butt_tool_service import bubble_butt_tool_service
        sex = self._validate_sex(str(manifest.get("sex") or ""))
        body = manifest.get("body") or {}
        if body:
            row = db.execute(select(BodyProportionWorkflowConfig).where(BodyProportionWorkflowConfig.sex == sex)).scalar_one_or_none()
            limits = self._normalize_limits(body.get("limits") or DEFAULT_LIMITS)
            formula = self._validate_formula(body.get("formula") or DEFAULT_FORMULA, limits)
            payload = {
                "workflow_json": body.get("workflow"),
                "input_mapping_json": body.get("input_mapping") or {},
                "limits_json": limits,
                "formula_json": formula,
                "fixed_values_json": self._deep_merge(DEFAULT_FIXED_VALUES, body.get("fixed_values") or {}),
                "storage_mode": self._validate_storage_mode(target),
                "is_enabled": bool(body.get("is_enabled", False)),
                "notes": body.get("notes"),
            }
            if row is None:
                row = BodyProportionWorkflowConfig(sex=sex, active_preview_source="auto", **payload)
                db.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
                db.add(row)
            db.commit()

        bubble = manifest.get("bubble_butt") or {}
        if bubble:
            row = db.execute(select(BubbleButtWorkflowConfig).where(BubbleButtWorkflowConfig.sex == sex)).scalar_one_or_none()
            payload = {
                "workflow_json": bubble.get("workflow"),
                "input_mapping_json": bubble.get("input_mapping") or {},
                "bubble_values_json": bubble_butt_tool_service._validate_values(
                    bubble.get("bubble_values") or [0.0, 0.4, 0.8, 1.2]
                ),
                "is_enabled": bool(bubble.get("is_enabled", False)),
                "notes": bubble.get("notes"),
            }
            if len(payload["bubble_values_json"]) != 4:
                raise ValueError("Imported Bubble Butt configuration requires exactly four values.")
            if row is None:
                row = BubbleButtWorkflowConfig(sex=sex, **payload)
                db.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
                db.add(row)
            db.commit()


    @staticmethod
    def _single_save_image_node_id(workflow: dict[str, Any]) -> str:
        save_nodes = [
            str(node_id)
            for node_id, node in workflow.items()
            if isinstance(node, dict) and str(node.get("class_type") or "") == "SaveImage"
        ]
        if not save_nodes:
            raise ValueError(
                "The Body Proportion workflow has no SaveImage node. "
                "Add exactly one Save Image node for the final result."
            )
        if len(save_nodes) > 1:
            raise ValueError(
                "The Body Proportion workflow has multiple SaveImage nodes "
                f"({', '.join(save_nodes)}). Keep exactly one final Save Image node "
                "so the tool never guesses which image is the preset result."
            )
        return save_nodes[0]

    def generate(self, db: Session, preset_id: int) -> tuple[BodyProportionPreset, str, str, bool]:
        preset = self.get_preset(db, preset_id); config = self.get_config(db, preset.sex)

        # Shared single-execution guard across Body Proportions and Bubble Butt.
        # Prevents a second local ComfyUI prompt from starting from another card,
        # tab or direct API request while one generation is already active.
        active_body = db.execute(
            select(BodyProportionPreset.id).where(
                BodyProportionPreset.sex == preset.sex,
                BodyProportionPreset.status == "generating",
                BodyProportionPreset.id != preset.id,
            ).limit(1)
        ).scalar_one_or_none()
        active_bubble = db.execute(
            select(BubbleButtPreset.id).where(
                BubbleButtPreset.sex == preset.sex,
                BubbleButtPreset.status == "generating",
            ).limit(1)
        ).scalar_one_or_none()
        if preset.status == "generating" or active_body is not None or active_bubble is not None:
            raise ValueError("No es posible ejecutar dos generaciones de Body Proportions/Bubble Butt al mismo tiempo.")

        if not config["is_enabled"] or not config["workflow"]: raise ValueError(f"The {preset.sex} workflow is not configured/enabled.")
        self._assert_limits(config, {k: getattr(preset, k) for k in ("hips_size", "fat_thin", "breasts_size", "skin_tone", "hair_length")})
        # Canonical values stay untouched in DB/storage/metadata.  The clothing-preview
        # workflow needs an execution-only breast boost for the two largest core bands
        # because Klein visually compresses those sizes after dressing the subject.
        values = {"hips_size": preset.hips_size, "fat_thin": preset.fat_thin, "breasts_size": preset.breasts_size,
                  "skin_tone": preset.skin_tone, "hair_length": preset.hair_length,
                  "category_name": preset.display_name, "sex": preset.sex == "woman"}
        execution_values = dict(values)
        # Strict preflight on the exact workflow stored in this tool.
        # This validation never mutates or repairs the workflow.
        self._validate_original_workflow_required_inputs(config["workflow"])
        workflow = self._patch_workflow(config["workflow"], config["input_mapping"], execution_values)
        output_node_id = self._single_save_image_node_id(workflow)
        preset.status = "generating"; preset.last_error = None; db.add(preset); db.commit()
        try:
            queued = comfyui_local_adapter_service.queue_prompt(
                workflow=workflow,
                extra_data={"body_proportion_profile": preset.profile_key},
                preserve_workflow_paths=True,
            )
            execution = comfyui_local_adapter_service.execute_queued_prompt(
                prompt_id=queued["prompt_id"], client_id=queued["client_id"],
                job_public_id=f"body-proportion-{preset.id}-{uuid4().hex[:8]}", timeout_seconds=900, download_outputs=True,
                prefer_api_view=True,
                allowed_node_ids={output_node_id},
            )
            image_output = next((item for item in execution.get("outputs", []) if str(item.get("content_type") or "").startswith("image/")), None)
            if not image_output: raise RuntimeError("The ComfyUI workflow completed without an image output.")
            content = Path(image_output["local_path"]).read_bytes(); content_type = image_output.get("content_type") or "image/png"
            previous_map = self._preview_storage_map(db, preset)
            overwritten = bool(previous_map or preset.image_storage_file_id)
            target_provider = self._resolved_storage_provider(db, config["storage_mode"])
            old_target = db.get(StorageFile, previous_map.get(target_provider)) if previous_map.get(target_provider) else None

            folder = "/".join(["body-proportion-presets", f"proportions_{preset.sex}", *self._category_parts(preset)])
            stored = self._save_selected(db, mode=config["storage_mode"], content=content,
                                         filename=f"{preset.category_slug}.png", content_type=content_type, folder=folder)

            next_map = dict(previous_map)
            next_map[target_provider] = stored.id
            preset.preview_storage_json = next_map
            preset.image_storage_file_id = stored.id
            preset.local_mirror_path = self._write_mirror(preset, content, content_type)
            preset.status = "ready"; preset.generated_at = utc_now(); preset.last_error = None
            preset.generation_metadata_json = {"prompt_id": queued["prompt_id"], "provider": "comfyui_local",
                                               "storage_mode": config["storage_mode"], "storage_provider": stored.provider, "values": values,
                                               "preview_execution_values": execution_values}
            db.add(preset); db.commit(); db.refresh(preset)

            if old_target and old_target.id != stored.id:
                try:
                    storage_service.delete_file(db, storage_file=old_target)
                    db.delete(old_target)
                    db.commit()
                except Exception:
                    db.rollback()

            try: Path(image_output["local_path"]).unlink(missing_ok=True)
            except OSError: pass
            return preset, queued["prompt_id"], stored.provider, overwritten
        except Exception as error:
            preset.status = "error"; preset.last_error = str(error); db.add(preset); db.commit(); db.refresh(preset); raise

    def response(self, db: Session, row: BodyProportionPreset) -> dict:
        image_url = None
        selected_storage_file_id = None

        # BackOffice Body Proportions MUST follow this tool's generation storage.
        # AppWeb/Create Model IA continues to use active_preview_source independently.
        config = self.get_config(db, row.sex)
        selected_source = config["storage_mode"]
        selected_provider = self._resolved_storage_provider(db, selected_source)

        stored = self.preview_storage_file(db, row, source=selected_source)

        # Legacy-safe fallback is allowed ONLY when the legacy file belongs to the
        # exact provider selected for generation. Never leak another provider here.
        if stored is None and row.image_storage_file_id:
            legacy = db.get(StorageFile, row.image_storage_file_id)
            if legacy and storage_service.provider_for_file(legacy) == selected_provider:
                stored = legacy

        if stored and storage_service.provider_for_file(stored) == selected_provider:
            selected_storage_file_id = stored.id
            image_url = storage_service.create_presigned_url(db, storage_file=stored)

        return {
            "id": row.id, "sex": row.sex, "sort_order": row.sort_order, "profile_key": row.profile_key,
            "display_name": row.display_name, "category_slug": row.category_slug,
            "fat_band": row.fat_band, "ass_band": row.ass_band, "breast_band": row.breast_band,
            "is_base_category": bool(row.is_base_category), "base_category_key": row.base_category_key,
            "hips_size": row.hips_size, "fat_thin": row.fat_thin, "breasts_size": row.breasts_size,
            "skin_tone": row.skin_tone, "hair_length": row.hair_length,
            "image_storage_file_id": selected_storage_file_id, "image_url": image_url,
            "local_mirror_path": row.local_mirror_path, "status": row.status, "last_error": row.last_error,
            "generation_metadata": row.generation_metadata_json or {}, "generated_at": row.generated_at,
            "created_at": row.created_at, "updated_at": row.updated_at,
        }


body_proportion_tool_service = BodyProportionToolService()

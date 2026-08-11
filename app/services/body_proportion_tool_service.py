import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import StorageProvider
from app.common.time import utc_now
from app.core.config import settings
from app.models.body_proportion_tool import BodyProportionPreset, BodyProportionWorkflowConfig
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
        fat_order, ass_order, breast_order = self._formula_orders(normalized)
        matrix = normalized.setdefault("ass_breast_compensation", {})
        for ass_key in ass_order:
            row = matrix.setdefault(ass_key, {})
            for breast_key in breast_order:
                row.setdefault(breast_key, 0.0)
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
            "limits": self._deep_merge(DEFAULT_LIMITS, row.limits_json),
            "formula": self._normalize_formula(row.formula_json or {}),
            "fixed_values": self._deep_merge(DEFAULT_FIXED_VALUES, row.fixed_values_json),
            "storage_mode": self._validate_storage_mode(getattr(row, "storage_mode", "auto")),
            "is_enabled": bool(row.is_enabled),
            "notes": row.notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def upsert_config(self, db: Session, sex: str, data) -> dict:
        sex = self._validate_sex(sex)
        row = db.execute(select(BodyProportionWorkflowConfig).where(BodyProportionWorkflowConfig.sex == sex)).scalar_one_or_none()
        limits = self._deep_merge(DEFAULT_LIMITS, data.limits)
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
        return {"created": created, "existing": existing, "removed": removed, "total_base": len(expected)}

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

    def reset_tool(self, db: Session, sex: str) -> dict:
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
        deleted_config = bool(config_row)
        if config_row:
            db.delete(config_row)
            db.commit()

        root = Path(str(getattr(settings, "LOCAL_STORAGE_DIR", "storage"))) / "body-proportions-library" / f"proportions_{sex}"
        mirror_removed = root.exists()
        if mirror_removed:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        return {
            "sex": sex,
            "deleted_presets": len(rows),
            "deleted_storage_files": deleted_storage,
            "deleted_config": deleted_config,
            "mirror_removed": mirror_removed,
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

    def generate(self, db: Session, preset_id: int) -> tuple[BodyProportionPreset, str, str, bool]:
        preset = self.get_preset(db, preset_id); config = self.get_config(db, preset.sex)
        if not config["is_enabled"] or not config["workflow"]: raise ValueError(f"The {preset.sex} workflow is not configured/enabled.")
        self._assert_limits(config, {k: getattr(preset, k) for k in ("hips_size", "fat_thin", "breasts_size", "skin_tone", "hair_length")})
        values = {"hips_size": preset.hips_size, "fat_thin": preset.fat_thin, "breasts_size": preset.breasts_size,
                  "skin_tone": preset.skin_tone, "hair_length": preset.hair_length,
                  "category_name": preset.display_name, "sex": preset.sex == "woman"}
        # Strict preflight on the exact workflow stored in this tool.
        # This validation never mutates or repairs the workflow.
        self._validate_original_workflow_required_inputs(config["workflow"])
        workflow = self._patch_workflow(config["workflow"], config["input_mapping"], values)
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
            )
            image_output = next((item for item in execution.get("outputs", []) if str(item.get("content_type") or "").startswith("image/")), None)
            if not image_output: raise RuntimeError("The ComfyUI workflow completed without an image output.")
            content = Path(image_output["local_path"]).read_bytes(); content_type = image_output.get("content_type") or "image/png"
            overwritten = bool(preset.image_storage_file_id)
            if preset.image_storage_file_id:
                old = db.get(StorageFile, preset.image_storage_file_id); preset.image_storage_file_id = None; db.add(preset); db.commit()
                if old:
                    storage_service.delete_file(db, storage_file=old); db.delete(old); db.commit()
            folder = "/".join(["body-proportion-presets", f"proportions_{preset.sex}", *self._category_parts(preset)])
            stored = self._save_selected(db, mode=config["storage_mode"], content=content,
                                         filename=f"{preset.category_slug}.png", content_type=content_type, folder=folder)
            preset.image_storage_file_id = stored.id; preset.local_mirror_path = self._write_mirror(preset, content, content_type)
            preset.status = "ready"; preset.generated_at = utc_now(); preset.last_error = None
            preset.generation_metadata_json = {"prompt_id": queued["prompt_id"], "provider": "comfyui_local",
                                               "storage_mode": config["storage_mode"], "storage_provider": stored.provider, "values": values}
            db.add(preset); db.commit(); db.refresh(preset)
            try: Path(image_output["local_path"]).unlink(missing_ok=True)
            except OSError: pass
            return preset, queued["prompt_id"], stored.provider, overwritten
        except Exception as error:
            preset.status = "error"; preset.last_error = str(error); db.add(preset); db.commit(); db.refresh(preset); raise

    def response(self, db: Session, row: BodyProportionPreset) -> dict:
        image_url = None
        if row.image_storage_file_id:
            stored = db.get(StorageFile, row.image_storage_file_id)
            if stored: image_url = storage_service.create_presigned_url(db, storage_file=stored)
        return {
            "id": row.id, "sex": row.sex, "sort_order": row.sort_order, "profile_key": row.profile_key,
            "display_name": row.display_name, "category_slug": row.category_slug,
            "fat_band": row.fat_band, "ass_band": row.ass_band, "breast_band": row.breast_band,
            "is_base_category": bool(row.is_base_category), "base_category_key": row.base_category_key,
            "hips_size": row.hips_size, "fat_thin": row.fat_thin, "breasts_size": row.breasts_size,
            "skin_tone": row.skin_tone, "hair_length": row.hair_length,
            "image_storage_file_id": row.image_storage_file_id, "image_url": image_url,
            "local_mirror_path": row.local_mirror_path, "status": row.status, "last_error": row.last_error,
            "generation_metadata": row.generation_metadata_json or {}, "generated_at": row.generated_at,
            "created_at": row.created_at, "updated_at": row.updated_at,
        }


body_proportion_tool_service = BodyProportionToolService()

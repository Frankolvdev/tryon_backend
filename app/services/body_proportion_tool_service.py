import json
import re
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.core.config import settings
from app.models.body_proportion_tool import BodyProportionPreset, BodyProportionWorkflowConfig
from app.models.storage_file import StorageFile
from app.schemas.body_proportion_tool import DEFAULT_FIXED_VALUES, DEFAULT_FORMULA, DEFAULT_LIMITS
from app.services.comfyui_local_adapter_service import comfyui_local_adapter_service
from app.services.storage_service import storage_service


class BodyProportionToolService:
    SEXES = {"woman", "man"}
    PATCH_KEYS = ("hips_size", "fat_thin", "breasts_size", "skin_tone", "hair_length", "category_name", "sex")

    def _validate_sex(self, sex: str) -> str:
        normalized = str(sex).strip().lower()
        if normalized not in self.SEXES:
            raise ValueError("sex must be woman or man")
        return normalized

    def _default_config(self, sex: str) -> dict:
        return {
            "id": None,
            "sex": sex,
            "workflow": None,
            "input_mapping": {},
            "limits": dict(DEFAULT_LIMITS),
            "formula": dict(DEFAULT_FORMULA),
            "fixed_values": dict(DEFAULT_FIXED_VALUES),
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
            "limits": {**DEFAULT_LIMITS, **(row.limits_json or {})},
            "formula": {**DEFAULT_FORMULA, **(row.formula_json or {})},
            "fixed_values": {**DEFAULT_FIXED_VALUES, **(row.fixed_values_json or {})},
            "is_enabled": bool(row.is_enabled),
            "notes": row.notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def upsert_config(self, db: Session, sex: str, data) -> dict:
        sex = self._validate_sex(sex)
        row = db.execute(select(BodyProportionWorkflowConfig).where(BodyProportionWorkflowConfig.sex == sex)).scalar_one_or_none()
        payload = {
            "workflow_json": data.workflow,
            "input_mapping_json": data.input_mapping,
            "limits_json": {**DEFAULT_LIMITS, **data.limits},
            "formula_json": {**DEFAULT_FORMULA, **data.formula},
            "fixed_values_json": {**DEFAULT_FIXED_VALUES, **data.fixed_values},
            "is_enabled": bool(data.is_enabled),
            "notes": data.notes,
        }
        if row is None:
            row = BodyProportionWorkflowConfig(sex=sex, **payload)
            db.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return self.get_config(db, sex)

    @staticmethod
    def _slug(value: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
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
            low = limits.get(low_key)
            high = limits.get(high_key)
            if low is not None and value < float(low):
                raise ValueError(f"{field}={value} is below configured minimum {low}.")
            if high is not None and value > float(high):
                raise ValueError(f"{field}={value} exceeds configured maximum {high}.")

    def create_preset(self, db: Session, data) -> BodyProportionPreset:
        sex = self._validate_sex(data.sex)
        config = self.get_config(db, sex)
        fixed = config["fixed_values"]
        values = {
            "hips_size": data.hips_size,
            "fat_thin": data.fat_thin,
            "breasts_size": data.breasts_size,
            "skin_tone": fixed.get("skin_tone", 0.0) if data.skin_tone is None else data.skin_tone,
            "hair_length": fixed.get("hair_length", 0.0) if data.hair_length is None else data.hair_length,
        }
        self._assert_limits(config, values)
        key, slug = self._next_identity(db, sex)
        row = BodyProportionPreset(
            sex=sex,
            sort_order=data.sort_order if data.sort_order is not None else self._next_sort_order(db, sex),
            profile_key=key,
            display_name=(data.display_name or key).strip(),
            category_slug=slug,
            **values,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list_presets(self, db: Session, sex: str) -> list[BodyProportionPreset]:
        sex = self._validate_sex(sex)
        return list(db.execute(select(BodyProportionPreset).where(BodyProportionPreset.sex == sex).order_by(BodyProportionPreset.sort_order.asc(), BodyProportionPreset.id.asc())).scalars().all())

    def get_preset(self, db: Session, preset_id: int) -> BodyProportionPreset:
        row = db.get(BodyProportionPreset, preset_id)
        if not row:
            raise LookupError("Body proportion preset not found.")
        return row

    def update_preset(self, db: Session, preset_id: int, data) -> BodyProportionPreset:
        row = self.get_preset(db, preset_id)
        patch = data.model_dump(exclude_unset=True)
        values = {
            "hips_size": patch.get("hips_size", row.hips_size),
            "fat_thin": patch.get("fat_thin", row.fat_thin),
            "breasts_size": patch.get("breasts_size", row.breasts_size),
            "skin_tone": patch.get("skin_tone", row.skin_tone),
            "hair_length": patch.get("hair_length", row.hair_length),
        }
        self._assert_limits(self.get_config(db, row.sex), values)
        for field, value in patch.items():
            setattr(row, field, value)
        if any(field in patch for field in values):
            row.status = "draft"
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def create_next(self, db: Session, preset_id: int, display_name: str | None = None) -> BodyProportionPreset:
        current = self.get_preset(db, preset_id)
        config = self.get_config(db, current.sex)
        formula = config["formula"]
        fat_delta = float(formula.get("fat_step", 0.0))
        hips_delta = float(formula.get("hips_step", 0.0)) + float(formula.get("fat_to_hips", 0.0)) * fat_delta
        breasts_delta = (
            float(formula.get("breasts_step", 0.0))
            + float(formula.get("fat_to_breasts", 0.0)) * fat_delta
            + float(formula.get("hips_to_breasts", 0.0)) * hips_delta
        )
        created = type("PresetInput", (), {
            "sex": current.sex,
            "sort_order": current.sort_order + 50.0,
            "display_name": display_name or f"Next after {current.profile_key}",
            "hips_size": current.hips_size + hips_delta,
            "fat_thin": current.fat_thin + fat_delta,
            "breasts_size": current.breasts_size + breasts_delta,
            "skin_tone": current.skin_tone,
            "hair_length": current.hair_length,
        })()
        return self.create_preset(db, created)

    def interpolate(self, db: Session, data) -> BodyProportionPreset:
        before = self.get_preset(db, data.before_id)
        after = self.get_preset(db, data.after_id)
        if before.sex != after.sex:
            raise ValueError("Cannot interpolate presets from different sexes.")
        ratio = float(data.ratio)
        def mix(a, b): return float(a) + (float(b) - float(a)) * ratio
        created = type("PresetInput", (), {
            "sex": before.sex,
            "sort_order": mix(before.sort_order, after.sort_order),
            "display_name": data.display_name or f"Intermediate {before.profile_key} / {after.profile_key}",
            "hips_size": mix(before.hips_size, after.hips_size),
            "fat_thin": mix(before.fat_thin, after.fat_thin),
            "breasts_size": mix(before.breasts_size, after.breasts_size),
            "skin_tone": mix(before.skin_tone, after.skin_tone),
            "hair_length": mix(before.hair_length, after.hair_length),
        })()
        return self.create_preset(db, created)

    def delete_preset(self, db: Session, preset_id: int) -> None:
        row = self.get_preset(db, preset_id)
        if row.image_storage_file_id:
            stored = db.get(StorageFile, row.image_storage_file_id)
            if stored:
                try:
                    storage_service.delete_file(db, storage_file=stored)
                finally:
                    db.delete(stored)
        db.delete(row)
        db.commit()

    def _patch_workflow(self, workflow: dict, mapping: dict, values: dict) -> dict:
        result = deepcopy(workflow)
        for key in self.PATCH_KEYS:
            target = mapping.get(key)
            if not target:
                continue
            node_id = str(target.get("node_id", "")).strip()
            input_name = str(target.get("input_name", "")).strip()
            if not node_id or not input_name:
                continue
            node = result.get(node_id)
            if not isinstance(node, dict):
                raise ValueError(f"Mapped ComfyUI node {node_id} for {key} does not exist.")
            inputs = node.setdefault("inputs", {})
            if not isinstance(inputs, dict):
                raise ValueError(f"Mapped ComfyUI node {node_id} has no inputs object.")
            inputs[input_name] = values[key]
        return result

    def _mirror_dir(self, preset: BodyProportionPreset) -> Path:
        root = Path(str(getattr(settings, "LOCAL_STORAGE_DIR", "storage"))) / "body-proportions-library"
        return root / f"proportions_{preset.sex}" / preset.category_slug

    def _write_mirror(self, preset: BodyProportionPreset, content: bytes, content_type: str | None) -> str:
        directory = self._mirror_dir(preset)
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".png" if not content_type or "png" in content_type else ".jpg"
        image_path = directory / f"preview{suffix}"
        for existing in directory.glob("preview.*"):
            if existing != image_path:
                existing.unlink(missing_ok=True)
        image_path.write_bytes(content)
        values = {
            "profile_key": preset.profile_key,
            "display_name": preset.display_name,
            "sex": preset.sex,
            "hips_size": preset.hips_size,
            "fat_thin": preset.fat_thin,
            "breasts_size": preset.breasts_size,
            "skin_tone": preset.skin_tone,
            "hair_length": preset.hair_length,
        }
        (directory / "values.json").write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / "values.txt").write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")
        return str(directory)

    def generate(self, db: Session, preset_id: int) -> tuple[BodyProportionPreset, str, str, bool]:
        preset = self.get_preset(db, preset_id)
        config = self.get_config(db, preset.sex)
        if not config["is_enabled"] or not config["workflow"]:
            raise ValueError(f"The {preset.sex} workflow is not configured/enabled.")
        self._assert_limits(config, {
            "hips_size": preset.hips_size, "fat_thin": preset.fat_thin,
            "breasts_size": preset.breasts_size, "skin_tone": preset.skin_tone,
            "hair_length": preset.hair_length,
        })
        values = {
            "hips_size": preset.hips_size,
            "fat_thin": preset.fat_thin,
            "breasts_size": preset.breasts_size,
            "skin_tone": preset.skin_tone,
            "hair_length": preset.hair_length,
            "category_name": preset.display_name,
            "sex": preset.sex == "woman",
        }
        workflow = self._patch_workflow(config["workflow"], config["input_mapping"], values)
        preset.status = "generating"; preset.last_error = None; db.add(preset); db.commit()
        try:
            queued = comfyui_local_adapter_service.queue_prompt(workflow=workflow, extra_data={"body_proportion_profile": preset.profile_key})
            execution = comfyui_local_adapter_service.execute_queued_prompt(
                prompt_id=queued["prompt_id"], client_id=queued["client_id"],
                job_public_id=f"body-proportion-{preset.id}-{uuid4().hex[:8]}",
                timeout_seconds=900, download_outputs=True,
            )
            image_output = next((item for item in execution.get("outputs", []) if str(item.get("content_type") or "").startswith("image/")), None)
            if not image_output:
                raise RuntimeError("The ComfyUI workflow completed without an image output.")
            content = Path(image_output["local_path"]).read_bytes()
            content_type = image_output.get("content_type") or "image/png"
            overwritten = bool(preset.image_storage_file_id)
            if preset.image_storage_file_id:
                old = db.get(StorageFile, preset.image_storage_file_id)
                preset.image_storage_file_id = None; db.add(preset); db.commit()
                if old:
                    storage_service.delete_file(db, storage_file=old)
                    db.delete(old); db.commit()
            stored = storage_service.save_bytes(
                db, user_id=None, content=content,
                original_filename=f"{preset.category_slug}.png",
                content_type=content_type,
                folder=f"body-proportion-presets/{preset.sex}/{preset.category_slug}",
            )
            preset.image_storage_file_id = stored.id
            preset.local_mirror_path = self._write_mirror(preset, content, content_type)
            preset.status = "ready"
            preset.generated_at = utc_now()
            preset.generation_metadata_json = {
                "prompt_id": queued["prompt_id"],
                "provider": "comfyui_local",
                "storage_provider": stored.provider,
                "values": values,
            }
            preset.last_error = None
            db.add(preset); db.commit(); db.refresh(preset)
            try:
                Path(image_output["local_path"]).unlink(missing_ok=True)
            except OSError:
                pass
            return preset, queued["prompt_id"], stored.provider, overwritten
        except Exception as error:
            preset.status = "error"; preset.last_error = str(error); db.add(preset); db.commit(); db.refresh(preset)
            raise

    def response(self, db: Session, row: BodyProportionPreset) -> dict:
        image_url = None
        if row.image_storage_file_id:
            stored = db.get(StorageFile, row.image_storage_file_id)
            if stored:
                image_url = storage_service.create_presigned_url(db, storage_file=stored)
        return {
            "id": row.id, "sex": row.sex, "sort_order": row.sort_order,
            "profile_key": row.profile_key, "display_name": row.display_name,
            "category_slug": row.category_slug, "hips_size": row.hips_size,
            "fat_thin": row.fat_thin, "breasts_size": row.breasts_size,
            "skin_tone": row.skin_tone, "hair_length": row.hair_length,
            "image_storage_file_id": row.image_storage_file_id, "image_url": image_url,
            "local_mirror_path": row.local_mirror_path, "status": row.status,
            "last_error": row.last_error, "generation_metadata": row.generation_metadata_json or {},
            "generated_at": row.generated_at, "created_at": row.created_at, "updated_at": row.updated_at,
        }


body_proportion_tool_service = BodyProportionToolService()

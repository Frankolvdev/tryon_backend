import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.core.config import settings
from app.models.body_proportion_tool import (
    BodyProportionPreset,
    BubbleButtPreset,
    BubbleButtWorkflowConfig,
)
from app.models.storage_file import StorageFile
from app.services.body_proportion_tool_service import body_proportion_tool_service
from app.services.comfyui_local_adapter_service import comfyui_local_adapter_service
from app.services.storage_service import storage_service


class BubbleButtToolService:
    PATCH_KEYS = (
        "hips_size", "fat_thin", "breasts_size", "bubble_butt",
        "skin_tone", "hair_length", "category_name", "sex",
    )

    def _validate_sex(self, sex: str) -> str:
        return body_proportion_tool_service._validate_sex(sex)

    @staticmethod
    def _validate_values(values: list[float] | None) -> list[float]:
        default_values = [0.0, 0.4, 0.8, 1.2]
        raw = list(values or default_values)

        # Backward compatibility with the first Bubble Butt version, which had
        # only three variants. Preserve custom legacy values by prepending the
        # new neutral variant; upgrade untouched [0,0,0] to the new defaults.
        if len(raw) == 3:
            legacy = [float(v) for v in raw]
            if legacy == [0.0, 0.0, 0.0]:
                return default_values
            return [0.0, *legacy]

        if len(raw) != 4:
            raise ValueError("Bubble Butt requires exactly four global values.")
        return [float(v) for v in raw]

    def default_config(self, sex: str) -> dict[str, Any]:
        sex = self._validate_sex(sex)
        return {
            "id": None, "sex": sex, "workflow": None, "input_mapping": {},
            "bubble_values": [0.0, 0.4, 0.8, 1.2], "is_enabled": False,
            "notes": None, "created_at": None, "updated_at": None,
        }

    def get_config(self, db: Session, sex: str) -> dict[str, Any]:
        sex = self._validate_sex(sex)
        row = db.execute(select(BubbleButtWorkflowConfig).where(BubbleButtWorkflowConfig.sex == sex)).scalar_one_or_none()
        if row is None:
            return self.default_config(sex)
        return {
            "id": row.id, "sex": row.sex, "workflow": row.workflow_json,
            "input_mapping": row.input_mapping_json or {},
            "bubble_values": self._validate_values(row.bubble_values_json),
            "is_enabled": bool(row.is_enabled), "notes": row.notes,
            "created_at": row.created_at, "updated_at": row.updated_at,
        }

    def upsert_config(self, db: Session, sex: str, data) -> dict[str, Any]:
        sex = self._validate_sex(sex)
        values = self._validate_values(data.bubble_values)
        row = db.execute(select(BubbleButtWorkflowConfig).where(BubbleButtWorkflowConfig.sex == sex)).scalar_one_or_none()
        payload = {
            "workflow_json": data.workflow,
            "input_mapping_json": data.input_mapping,
            "bubble_values_json": values,
            "is_enabled": bool(data.is_enabled),
            "notes": data.notes,
        }
        if row is None:
            row = BubbleButtWorkflowConfig(sex=sex, **payload)
            db.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        db.commit()
        db.refresh(row)
        # Keep the derived Bubble matrix aligned with any changed global values.
        self.sync_matrix(db, sex)
        body_proportion_tool_service.write_configuration_manifest(db, sex)
        return self.get_config(db, sex)

    def readiness(self, db: Session, sex: str) -> dict[str, Any]:
        sex = self._validate_sex(sex)
        body_proportion_tool_service.ensure_defaults(db, sex)
        body_config = body_proportion_tool_service.get_config(db, sex)
        rows = db.execute(select(BodyProportionPreset).where(
            BodyProportionPreset.sex == sex,
            BodyProportionPreset.is_base_category.is_(True),
        ).order_by(BodyProportionPreset.sort_order.asc())).scalars().all()

        missing = []
        for row in rows:
            if row.status != "ready":
                missing.append({"preset_id": row.id, "profile_key": row.profile_key, "reason": f"status={row.status}"})
                continue
            stored = body_proportion_tool_service.preview_storage_file(db, row, source=body_config["storage_mode"])
            if stored is None:
                missing.append({"preset_id": row.id, "profile_key": row.profile_key, "reason": "preview missing in generation provider"})
        return {
            "sex": sex,
            "required": len(rows),
            "ready": len(rows) - len(missing),
            "missing_count": len(missing),
            "complete": len(rows) > 0 and not missing,
            "missing": missing,
        }

    def _grid_values(self, body_config: dict[str, Any], fat_band: str, ass_band: str) -> dict[str, float]:
        _, _, breast_order = body_proportion_tool_service._formula_orders(body_config["formula"])
        if not breast_order:
            raise ValueError("Body Proportions has no breast anchors.")
        huge_breast_key = "huge" if "huge" in body_config["formula"].get("breast_levels", {}) else breast_order[-1]
        # Dynamic Huge Breast: use the explicit Huge anchor when present, including
        # the current Fat/Hips compensation for this exact row.
        values = body_proportion_tool_service._base_values(body_config, fat_band, ass_band, huge_breast_key)
        return values

    def sync_matrix(self, db: Session, sex: str) -> dict[str, int]:
        sex = self._validate_sex(sex)
        body_config = body_proportion_tool_service.get_config(db, sex)
        bubble_config = self.get_config(db, sex)
        fat_order, ass_order, _ = body_proportion_tool_service._formula_orders(body_config["formula"])
        bubble_values = self._validate_values(bubble_config["bubble_values"])
        expected = {(fat, ass, variant) for fat in fat_order for ass in ass_order for variant in (1, 2, 3, 4)}

        existing_rows = db.execute(select(BubbleButtPreset).where(BubbleButtPreset.sex == sex)).scalars().all()
        removed = 0
        for row in existing_rows:
            if (row.fat_band, row.ass_band, row.variant_index) not in expected:
                self._delete_row(db, row)
                removed += 1

        created = updated = 0
        order = 100.0
        formula = body_config["formula"]
        for fat_band in fat_order:
            for ass_band in ass_order:
                base = self._grid_values(body_config, fat_band, ass_band)
                fat_label = formula["fat_levels"][fat_band]["label"]
                ass_label = formula["ass_levels"][ass_band]["label"]
                for variant in (1, 2, 3, 4):
                    bubble_value = bubble_values[variant - 1]
                    name = f"{fat_label} - {ass_label} - Bubble Butt {variant}"
                    key = f"BB:{fat_band}:{ass_band}:{variant}"
                    row = db.execute(select(BubbleButtPreset).where(
                        BubbleButtPreset.sex == sex,
                        BubbleButtPreset.fat_band == fat_band,
                        BubbleButtPreset.ass_band == ass_band,
                        BubbleButtPreset.variant_index == variant,
                    )).scalar_one_or_none()
                    next_values = {
                        "hips_size": float(base["hips_size"]),
                        "fat_thin": float(base["fat_thin"]),
                        "breasts_size": float(base["breasts_size"]),
                        "bubble_butt": float(bubble_value),
                        "skin_tone": float(base["skin_tone"]),
                        "hair_length": float(base["hair_length"]),
                    }
                    if row is None:
                        row = BubbleButtPreset(
                            sex=sex, sort_order=order, profile_key=key,
                            display_name=name, category_slug=body_proportion_tool_service._slug(name),
                            fat_band=fat_band, ass_band=ass_band, variant_index=variant,
                            **next_values,
                        )
                        db.add(row)
                        created += 1
                    else:
                        changed = any(float(getattr(row, k)) != float(v) for k, v in next_values.items())
                        row.sort_order = order
                        row.display_name = name
                        row.category_slug = body_proportion_tool_service._slug(name)
                        for k, v in next_values.items():
                            setattr(row, k, v)
                        if changed and row.status == "ready":
                            row.status = "draft"
                        db.add(row)
                        updated += 1
                    db.commit()
                    order += 100.0
        return {"created": created, "updated": updated, "removed": removed, "total": len(expected)}

    def list_presets(self, db: Session, sex: str) -> list[BubbleButtPreset]:
        sex = self._validate_sex(sex)
        self.sync_matrix(db, sex)
        return list(db.execute(select(BubbleButtPreset).where(
            BubbleButtPreset.sex == sex
        ).order_by(BubbleButtPreset.sort_order.asc(), BubbleButtPreset.id.asc())).scalars().all())

    def get_preset(self, db: Session, preset_id: int) -> BubbleButtPreset:
        row = db.get(BubbleButtPreset, preset_id)
        if row is None:
            raise LookupError("Bubble Butt preset not found.")
        return row

    def _storage_map(self, db: Session, row: BubbleButtPreset) -> dict[str, int]:
        mapping = {}
        for provider, raw_id in (row.preview_storage_json or {}).items():
            try:
                storage_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if db.get(StorageFile, storage_id):
                mapping[str(provider)] = storage_id
        if row.image_storage_file_id:
            stored = db.get(StorageFile, row.image_storage_file_id)
            if stored:
                mapping.setdefault(storage_service.provider_for_file(stored), stored.id)
        return mapping

    def preview_storage_file(self, db: Session, row: BubbleButtPreset, source: str | None = None) -> StorageFile | None:
        selected = source or body_proportion_tool_service.active_preview_source(db, row.sex)
        provider = body_proportion_tool_service._source_provider(db, selected)
        storage_id = self._storage_map(db, row).get(provider)
        if storage_id:
            return db.get(StorageFile, storage_id)
        return None

    @staticmethod
    def _parts(row: BubbleButtPreset) -> list[str]:
        return ["bubble_butt", row.fat_band, row.ass_band, f"variant_{row.variant_index}"]

    def _mirror_dir(self, row: BubbleButtPreset) -> Path:
        root = Path(str(getattr(settings, "LOCAL_STORAGE_DIR", "storage"))) / "body-proportions-library"
        return root / f"proportions_{row.sex}" / Path(*self._parts(row))

    def _write_mirror(self, row: BubbleButtPreset, content: bytes, content_type: str | None) -> str:
        directory = self._mirror_dir(row)
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".png" if not content_type or "png" in content_type else ".jpg"
        image_path = directory / f"preview{suffix}"
        for old in directory.glob("preview.*"):
            if old != image_path:
                old.unlink(missing_ok=True)
        image_path.write_bytes(content)
        values = self.metadata(row)
        (directory/"values.json").write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory/"values.txt").write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")
        return str(directory)

    def metadata(self, row: BubbleButtPreset) -> dict[str, Any]:
        return {
            "stage": "bubble_butt", "format_version": 1,
            "profile_key": row.profile_key, "display_name": row.display_name,
            "category_slug": row.category_slug, "sex": row.sex,
            "sort_order": row.sort_order, "fat_band": row.fat_band,
            "ass_band": row.ass_band, "variant_index": row.variant_index,
            "hips_size": row.hips_size, "fat_thin": row.fat_thin,
            "breasts_size": row.breasts_size, "bubble_butt": row.bubble_butt,
            "skin_tone": row.skin_tone, "hair_length": row.hair_length,
        }

    def _delete_row(self, db: Session, row: BubbleButtPreset) -> None:
        ids = set(self._storage_map(db, row).values())
        for storage_id in ids:
            stored = db.get(StorageFile, storage_id)
            if stored:
                try:
                    storage_service.delete_file(db, storage_file=stored)
                except Exception:
                    db.rollback()
                try:
                    db.delete(stored)
                    db.commit()
                except Exception:
                    db.rollback()
        db.delete(row)
        db.commit()

    def reset(self, db: Session, sex: str, *, delete_workflow_mappings: bool = False) -> dict[str, int | bool]:
        rows = list(db.execute(select(BubbleButtPreset).where(BubbleButtPreset.sex == sex)).scalars().all())
        for row in rows:
            self._delete_row(db, row)
        cfg = db.execute(select(BubbleButtWorkflowConfig).where(BubbleButtWorkflowConfig.sex == sex)).scalar_one_or_none()
        deleted_config = False
        if cfg:
            if delete_workflow_mappings:
                db.delete(cfg)
                deleted_config = True
            else:
                cfg.bubble_values_json = [0.0, 0.4, 0.8, 1.2]
                cfg.notes = None
                db.add(cfg)
            db.commit()
        return {"deleted_presets": len(rows), "deleted_config": deleted_config}

    def _patch_workflow(self, workflow: dict, mapping: dict, values: dict) -> dict:
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
            node = result.get(node_id)
            if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
                raise ValueError(f"Mapped Bubble Butt node {node_id} for {key} is invalid.")
            if input_name not in node["inputs"]:
                raise ValueError(f"Mapped Bubble Butt input {input_name!r} does not exist on node {node_id}.")
            node["inputs"][input_name] = deepcopy(values[key])
            allowed_paths.add((node_id, "inputs", input_name))

        unexpected = [
            (path, kind) for path, kind in body_proportion_tool_service._workflow_differences(original, result)
            if path not in allowed_paths
        ]
        if unexpected:
            preview = ", ".join(".".join(path) for path, _ in unexpected[:10])
            raise RuntimeError("Bubble Butt workflow integrity check failed. Unexpected changes: " + preview)
        return result

    def generate(self, db: Session, preset_id: int):
        row = self.get_preset(db, preset_id)

        # Single-execution guard for the local ComfyUI Body Proportions tool.
        # UI disabling is not enough: this also blocks double-clicks, another
        # browser tab or a direct API request while a generation is active.
        active_bubble = db.execute(
            select(BubbleButtPreset.id).where(
                BubbleButtPreset.sex == row.sex,
                BubbleButtPreset.status == "generating",
                BubbleButtPreset.id != row.id,
            ).limit(1)
        ).scalar_one_or_none()
        active_body = db.execute(
            select(BodyProportionPreset.id).where(
                BodyProportionPreset.sex == row.sex,
                BodyProportionPreset.status == "generating",
            ).limit(1)
        ).scalar_one_or_none()
        if row.status == "generating" or active_bubble is not None or active_body is not None:
            raise ValueError("No es posible ejecutar dos generaciones de Body Proportions/Bubble Butt al mismo tiempo.")

        readiness = self.readiness(db, row.sex)
        if not readiness["complete"]:
            raise ValueError(
                f"Bubble Butt is locked until Body Proportions is complete. "
                f"Missing {readiness['missing_count']} of {readiness['required']} previous previews."
            )
        bubble_cfg = self.get_config(db, row.sex)
        body_cfg = body_proportion_tool_service.get_config(db, row.sex)
        if not bubble_cfg["is_enabled"] or not bubble_cfg["workflow"]:
            raise ValueError("Bubble Butt workflow is not configured/enabled.")

        values = {
            "hips_size": row.hips_size, "fat_thin": row.fat_thin,
            "breasts_size": row.breasts_size, "bubble_butt": row.bubble_butt,
            "skin_tone": row.skin_tone, "hair_length": row.hair_length,
            "category_name": row.display_name, "sex": row.sex == "woman",
        }
        body_proportion_tool_service._validate_original_workflow_required_inputs(bubble_cfg["workflow"])
        workflow = self._patch_workflow(bubble_cfg["workflow"], bubble_cfg["input_mapping"], values)
        output_node_id = body_proportion_tool_service._single_save_image_node_id(workflow)
        row.status = "generating"
        row.last_error = None
        db.add(row)
        db.commit()
        try:
            queued = comfyui_local_adapter_service.queue_prompt(
                workflow=workflow,
                extra_data={"bubble_butt_profile": row.profile_key},
                preserve_workflow_paths=True,
            )
            execution = comfyui_local_adapter_service.execute_queued_prompt(
                prompt_id=queued["prompt_id"], client_id=queued["client_id"],
                job_public_id=f"bubble-butt-{row.id}-{uuid4().hex[:8]}",
                timeout_seconds=900, download_outputs=True, prefer_api_view=True,
                allowed_node_ids={output_node_id},
            )
            image_output = next((x for x in execution.get("outputs", []) if str(x.get("content_type") or "").startswith("image/")), None)
            if not image_output:
                raise RuntimeError("Bubble Butt workflow completed without an image output.")
            content = Path(image_output["local_path"]).read_bytes()
            content_type = image_output.get("content_type") or "image/png"
            previous_map = self._storage_map(db, row)
            target_provider = body_proportion_tool_service._resolved_storage_provider(db, body_cfg["storage_mode"])
            old_target = db.get(StorageFile, previous_map.get(target_provider)) if previous_map.get(target_provider) else None
            overwritten = bool(previous_map or row.image_storage_file_id)
            folder = "/".join([
                "body-proportion-presets", f"proportions_{row.sex}", *self._parts(row)
            ])
            stored = body_proportion_tool_service._save_selected(
                db, mode=body_cfg["storage_mode"], content=content,
                filename=f"{row.category_slug}.png", content_type=content_type, folder=folder,
            )
            next_map = dict(previous_map)
            next_map[target_provider] = stored.id
            row.preview_storage_json = next_map
            row.image_storage_file_id = stored.id
            row.local_mirror_path = self._write_mirror(row, content, content_type)
            row.status = "ready"
            row.last_error = None
            row.generated_at = utc_now()
            row.generation_metadata_json = {
                "prompt_id": queued["prompt_id"], "provider": "comfyui_local",
                "storage_mode": body_cfg["storage_mode"], "storage_provider": stored.provider,
                "values": values, "source_stage": "body_proportions",
                "huge_breast_dynamic": True,
            }
            db.add(row)
            db.commit()
            db.refresh(row)
            if old_target and old_target.id != stored.id:
                try:
                    storage_service.delete_file(db, storage_file=old_target)
                    db.delete(old_target)
                    db.commit()
                except Exception:
                    db.rollback()
            try:
                Path(image_output["local_path"]).unlink(missing_ok=True)
            except OSError:
                pass
            return row, queued["prompt_id"], stored.provider, overwritten
        except Exception as error:
            row.status = "error"
            row.last_error = str(error)
            db.add(row)
            db.commit()
            db.refresh(row)
            raise

    def response(self, db: Session, row: BubbleButtPreset) -> dict[str, Any]:
        body_cfg = body_proportion_tool_service.get_config(db, row.sex)
        selected_provider = body_proportion_tool_service._resolved_storage_provider(db, body_cfg["storage_mode"])
        stored = self.preview_storage_file(db, row, source=body_cfg["storage_mode"])
        selected_id = None
        image_url = None
        if stored and storage_service.provider_for_file(stored) == selected_provider:
            selected_id = stored.id
            image_url = storage_service.create_presigned_url(db, storage_file=stored)
        return {
            **self.metadata(row),
            "id": row.id, "image_storage_file_id": selected_id, "image_url": image_url,
            "local_mirror_path": row.local_mirror_path, "status": row.status,
            "last_error": row.last_error, "generation_metadata": row.generation_metadata_json or {},
            "generated_at": row.generated_at, "created_at": row.created_at, "updated_at": row.updated_at,
        }

    def ready_rows(self, db: Session, sex: str) -> list[BubbleButtPreset]:
        return list(db.execute(select(BubbleButtPreset).where(
            BubbleButtPreset.sex == sex, BubbleButtPreset.status == "ready"
        ).order_by(BubbleButtPreset.sort_order.asc())).scalars().all())

    def verify_source(self, db: Session, sex: str, source: str) -> dict[str, Any]:
        rows = self.ready_rows(db, sex)
        provider = body_proportion_tool_service._source_provider(db, source)
        verified = 0
        missing = []
        for row in rows:
            stored = self.preview_storage_file(db, row, source=source)
            if not stored or storage_service.provider_for_file(stored) != provider:
                missing.append({"preset_id": row.id, "profile_key": row.profile_key})
                continue
            try:
                if storage_service.read_bytes(db, storage_file=stored):
                    verified += 1
                else:
                    missing.append({"preset_id": row.id, "profile_key": row.profile_key})
            except Exception:
                missing.append({"preset_id": row.id, "profile_key": row.profile_key})
        return {"required": len(rows), "verified": verified, "missing": missing}

    def copy_ready(self, db: Session, sex: str, source: str, target: str) -> dict[str, int]:
        source_provider = body_proportion_tool_service._source_provider(db, source)
        target_provider = body_proportion_tool_service._source_provider(db, target)
        copied = skipped = failed = 0
        for row in self.ready_rows(db, sex):
            try:
                src = self.preview_storage_file(db, row, source=source)
                if not src or storage_service.provider_for_file(src) != source_provider:
                    failed += 1
                    continue
                existing = self.preview_storage_file(db, row, source=target)
                if existing and storage_service.provider_for_file(existing) == target_provider:
                    try:
                        if storage_service.read_bytes(db, storage_file=existing):
                            skipped += 1
                            continue
                    except Exception:
                        pass
                content = storage_service.read_bytes(db, storage_file=src)
                folder = "/".join(["body-proportion-library", f"proportions_{sex}", *self._parts(row)])
                stored = body_proportion_tool_service._save_selected(
                    db, mode=target, content=content,
                    filename=body_proportion_tool_service._portable_preview_name(src),
                    content_type=src.content_type or "image/png", folder=folder,
                )
                mapping = self._storage_map(db, row)
                mapping[target_provider] = stored.id
                row.preview_storage_json = mapping
                db.add(row)
                db.commit()
                copied += 1
            except Exception:
                db.rollback()
                failed += 1
        return {"copied": copied, "skipped": skipped, "failed": failed}

    def add_to_zip(self, archive, db: Session, sex: str, source: str) -> None:
        for row in self.ready_rows(db, sex):
            stored = self.preview_storage_file(db, row, source=source)
            if not stored:
                continue
            content = storage_service.read_bytes(db, storage_file=stored)
            folder = "/".join([f"proportions_{sex}", *self._parts(row)])
            metadata = self.metadata(row)
            archive.writestr(f"{folder}/{body_proportion_tool_service._portable_preview_name(stored)}", content)
            archive.writestr(f"{folder}/values.json", json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"))
            archive.writestr(f"{folder}/values.txt", "\n".join(f"{k}={v}" for k, v in metadata.items()).encode("utf-8"))

    def import_from_archive(self, archive, files, safe_paths, target: str) -> dict[str, Any]:
        imported = updated = created = 0
        errors = []
        metadata_files = [
            info for info in files
            if safe_paths[info.filename].name.lower() == "values.json"
            and "bubble_butt" in safe_paths[info.filename].parts
        ]
        for info in metadata_files:
            path = safe_paths[info.filename]
            try:
                metadata = json.loads(archive.read(info).decode("utf-8"))
                if metadata.get("stage") != "bubble_butt":
                    continue
                sex = self._validate_sex(str(metadata["sex"]))
                fat_band = str(metadata["fat_band"])
                ass_band = str(metadata["ass_band"])
                variant = int(metadata["variant_index"])
                row = db.execute(select(BubbleButtPreset).where(
                    BubbleButtPreset.sex == sex, BubbleButtPreset.fat_band == fat_band,
                    BubbleButtPreset.ass_band == ass_band, BubbleButtPreset.variant_index == variant,
                )).scalar_one_or_none()
                if row is None:
                    row = BubbleButtPreset(
                        sex=sex, sort_order=float(metadata.get("sort_order", 0)),
                        profile_key=str(metadata["profile_key"]), display_name=str(metadata["display_name"]),
                        category_slug=str(metadata["category_slug"]), fat_band=fat_band, ass_band=ass_band,
                        variant_index=variant, hips_size=float(metadata["hips_size"]),
                        fat_thin=float(metadata["fat_thin"]), breasts_size=float(metadata["breasts_size"]),
                        bubble_butt=float(metadata["bubble_butt"]), skin_tone=float(metadata["skin_tone"]),
                        hair_length=float(metadata["hair_length"]), preview_storage_json={},
                    )
                    db.add(row); db.flush(); created += 1
                else:
                    for key in ("hips_size", "fat_thin", "breasts_size", "bubble_butt", "skin_tone", "hair_length"):
                        setattr(row, key, float(metadata[key]))
                    updated += 1
                preview = next((x for x in files if safe_paths[x.filename].parent == path.parent and safe_paths[x.filename].name.lower() in {"preview.png","preview.jpg","preview.jpeg","preview.webp"}), None)
                if preview is None:
                    raise ValueError("Bubble Butt preview missing.")
                content = archive.read(preview)
                preview_path = safe_paths[preview.filename]
                folder = "/".join(["body-proportion-library", f"proportions_{sex}", *self._parts(row)])
                stored = body_proportion_tool_service._save_selected(
                    db, mode=target, content=content, filename=preview_path.name.lower(),
                    content_type="image/png" if preview_path.suffix.lower()==".png" else "image/jpeg", folder=folder,
                )
                mapping = self._storage_map(db, row)
                mapping[storage_service.provider_for_file(stored)] = stored.id
                row.preview_storage_json = mapping
                row.image_storage_file_id = stored.id
                row.local_mirror_path = self._write_mirror(row, content, stored.content_type)
                row.status = "ready"; row.last_error = None; row.generated_at = utc_now()
                db.add(row); db.commit(); imported += 1
            except Exception as error:
                db.rollback()
                errors.append({"path": info.filename, "error": str(error)})
        return {"imported": imported, "created": created, "updated": updated, "errors": errors}


bubble_butt_tool_service = BubbleButtToolService()

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.services.runtime_context_generator_service import RuntimeContextGeneratorService

ProgressCallback = Callable[[str, int, str], None]


class RuntimeModelVolumeExportService:
    """Exports only workflow-required models using ComfyUI's models layout."""

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _resolve(config: RuntimeBuilderConfig, comfyui_path: str) -> tuple[Path, list[dict[str, Any]]]:
        comfy = RuntimeContextGeneratorService._find_comfyui(comfyui_path)
        records: list[dict[str, Any]] = []
        for item in [m for m in (config.models or []) if m.get("enabled", True)]:
            source = RuntimeContextGeneratorService._find_model(comfy, item)
            record = dict(item)
            if source is None:
                record.update({"found": False, "source_path": None, "relative_path": None, "size_bytes": 0})
            else:
                relative = source.relative_to(comfy / "models")
                record.update({
                    "found": True,
                    "source_path": str(source),
                    "relative_path": f"models/{relative.as_posix()}",
                    "size_bytes": source.stat().st_size,
                })
            records.append(record)
        return comfy, records

    @staticmethod
    def analyze(config: RuntimeBuilderConfig, comfyui_path: str) -> dict[str, Any]:
        comfy, records = RuntimeModelVolumeExportService._resolve(config, comfyui_path)
        found = [item for item in records if item["found"]]
        missing = [item for item in records if not item["found"]]
        return {
            "source_comfyui": str(comfy),
            "models_detected": len(records),
            "models_found": len(found),
            "models_missing": len(missing),
            "bytes_total": sum(int(item["size_bytes"]) for item in found),
            "items": records,
        }

    @staticmethod
    def export(
        config: RuntimeBuilderConfig,
        payload: Any,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        notify = progress or (lambda _phase, _percent, _message: None)
        notify("analyzing", 2, "Localizando los modelos requeridos…")
        comfy, records = RuntimeModelVolumeExportService._resolve(config, payload.comfyui_path)

        base = (
            Path(payload.output_directory).expanduser().resolve()
            if payload.output_directory
            else (
                Path(config.export_root_directory).expanduser().resolve()
                if config.export_root_directory
                else Path(os.getenv("RUNTIME_EXPORTS_DIR", "runtime_exports")).resolve()
            )
        )
        output = base / f"{RuntimeContextGeneratorService._safe(config.project_key or config.name)}-models-volume"
        models_root = output / "models"
        output.mkdir(parents=True, exist_ok=True)
        models_root.mkdir(parents=True, exist_ok=True)

        copied = 0
        skipped = 0
        missing = 0
        bytes_copied = 0
        warnings: list[str] = []
        manifest_items: list[dict[str, Any]] = []
        total = max(1, len(records))

        for index, item in enumerate(records):
            record = dict(item)
            if not item["found"]:
                missing += 1
                record["status"] = "missing"
                warnings.append(f"Modelo no localizado: {item.get('target_path') or item.get('name')}")
                manifest_items.append(record)
                continue

            source = Path(str(item["source_path"]))
            relative = source.relative_to(comfy / "models")
            destination = models_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)

            source_hash: str | None = None
            should_copy = True
            if destination.exists():
                if payload.skip_identical and destination.stat().st_size == source.stat().st_size:
                    if payload.calculate_sha256:
                        source_hash = RuntimeModelVolumeExportService._sha256(source)
                        destination_hash = RuntimeModelVolumeExportService._sha256(destination)
                        should_copy = source_hash != destination_hash
                    else:
                        should_copy = False
                elif not payload.overwrite:
                    should_copy = False

            if should_copy:
                shutil.copy2(source, destination)
                copied += 1
                bytes_copied += source.stat().st_size
                status = "copied"
            else:
                skipped += 1
                status = "skipped"

            if payload.calculate_sha256 and source_hash is None:
                source_hash = RuntimeModelVolumeExportService._sha256(source)

            record.update({
                "status": status,
                "sha256": source_hash or item.get("sha256"),
                "destination_path": str(destination),
                "relative_path": f"models/{relative.as_posix()}",
            })
            manifest_items.append(record)
            notify(
                "copying",
                5 + int(88 * (index + 1) / total),
                f"Procesando modelo {index + 1} de {len(records)}…",
            )

        manifest = {
            "contract": "tryon.models-volume/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_key": config.project_key,
            "runtime_version": config.runtime_version,
            "source_comfyui": str(comfy),
            "volume_mount_path": "/app/ComfyUI/models",
            "models": manifest_items,
            "summary": {
                "models_detected": len(records),
                "models_found": len(records) - missing,
                "models_missing": missing,
                "models_copied": copied,
                "models_skipped": skipped,
                "bytes_copied": bytes_copied,
            },
        }
        manifest_path = output / "models_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        notify("completed", 99, "Modelos organizados para Volume.")
        return {
            "success": True,
            "output_directory": str(output),
            "models_directory": str(models_root),
            "manifest_path": str(manifest_path),
            "models_detected": len(records),
            "models_found": len(records) - missing,
            "models_missing": missing,
            "models_copied": copied,
            "models_skipped": skipped,
            "bytes_copied": bytes_copied,
            "warnings": warnings,
            "manifest": manifest,
        }

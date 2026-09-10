import io
import json
import re
import zipfile
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from sqlalchemy.orm import Session

from app.models.model_generation_asset import ModelGenerationAsset
from app.models.storage_file import StorageFile
from app.schemas.model_generation_asset import ModelGenerationAssetCreate, ModelGenerationAssetUpdate
from app.services.storage_service import StorageProvider, storage_service


class ModelGenerationAssetService:
    MODES = {"auto", "local", "amazon_s3", "cloudflare_r2"}
    TOOLS = {
        "eyebrows", "lips", "hairstyle", "facial_structures",
        "hips", "butt_size", "breasts", "height", "bubble_butt", "waist", "complexion",
        # Legacy aliases accepted so old bundles remain importable.
        "ass", "slim", "thick",
    }
    IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
    PRIVATE_TOOLS = {"facial_structures"}
    BODY_TOOLS = {"hips", "butt_size", "breasts", "height", "bubble_butt", "waist", "complexion"}
    LEGACY_TOOL_MAP = {"ass": "butt_size", "slim": "complexion", "thick": "complexion"}

    @classmethod
    def _canonical_tool(cls, tool_key: str) -> str:
        return cls.LEGACY_TOOL_MAP.get(tool_key, tool_key)

    @staticmethod
    def _slug(value: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        if not value:
            raise ValueError("Asset key cannot be empty.")
        return value[:120]

    def storage_options(self, db: Session) -> dict:
        return {
            "active_provider": storage_service.active_provider(db),
            "modes": ["auto", "local", "amazon_s3", "cloudflare_r2"],
        }

    def list(
        self,
        db: Session,
        *,
        tool_key: str | None = None,
        tool_keys: list[str] | None = None,
        active_only: bool = False,
        skip: int = 0,
        limit: int | None = None,
    ) -> list[ModelGenerationAsset]:
        query = db.query(ModelGenerationAsset)
        if tool_key and tool_keys:
            raise ValueError("Use tool_key or tool_keys, not both.")
        if tool_key:
            if tool_key not in self.TOOLS:
                raise ValueError("Unsupported tool key.")
            canonical = self._canonical_tool(tool_key)
            query = query.filter(ModelGenerationAsset.tool_key == canonical)
        elif tool_keys:
            unsupported = [item for item in tool_keys if item not in self.TOOLS]
            if unsupported:
                raise ValueError("Unsupported tool key.")
            canonical_tools = sorted({self._canonical_tool(item) for item in tool_keys})
            query = query.filter(ModelGenerationAsset.tool_key.in_(canonical_tools))
        if active_only:
            query = query.filter(ModelGenerationAsset.is_active.is_(True))
        query = query.order_by(ModelGenerationAsset.tool_key, ModelGenerationAsset.sort_order, ModelGenerationAsset.id)
        if skip:
            query = query.offset(skip)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count(self, db: Session, *, tool_key: str | None = None, active_only: bool = False) -> int:
        query = db.query(ModelGenerationAsset)
        if tool_key:
            if tool_key not in self.TOOLS:
                raise ValueError("Unsupported tool key.")
            query = query.filter(ModelGenerationAsset.tool_key == self._canonical_tool(tool_key))
        if active_only:
            query = query.filter(ModelGenerationAsset.is_active.is_(True))
        return query.count()

    def get(self, db: Session, asset_id: int) -> ModelGenerationAsset:
        row = db.get(ModelGenerationAsset, asset_id)
        if not row:
            raise ValueError("Model generation asset not found.")
        return row

    @staticmethod
    def _file(db: Session, file_id: int | None) -> StorageFile | None:
        return db.get(StorageFile, file_id) if file_id else None

    def response(self, db: Session, row: ModelGenerationAsset) -> dict:
        poster = self._file(db, row.poster_storage_file_id)
        video = self._file(db, row.video_storage_file_id)
        return {
            "id": row.id,
            "tool_key": row.tool_key,
            "asset_key": row.asset_key,
            "title": row.title,
            "value": row.value,
            "sort_order": row.sort_order,
            "position": row.position,
            "storage_mode": row.storage_mode,
            "poster_storage_file_id": row.poster_storage_file_id,
            "video_storage_file_id": row.video_storage_file_id,
            "poster_url": storage_service.create_presigned_url(db, storage_file=poster) if poster else None,
            "video_url": storage_service.create_presigned_url(db, storage_file=video) if video else None,
            "is_active": row.is_active,
            "notes": row.notes,
            "metadata": dict(row.metadata_json or {}),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def create(self, db: Session, data: ModelGenerationAssetCreate) -> ModelGenerationAsset:
        tool_key = self._canonical_tool(data.tool_key)
        key = self._slug(data.asset_key)
        if tool_key in self.BODY_TOOLS:
            if data.position is None:
                raise ValueError("Position is required for body preview assets.")
            position_exists = db.query(ModelGenerationAsset).filter(
                ModelGenerationAsset.tool_key == tool_key,
                ModelGenerationAsset.position == data.position,
            ).first()
            if position_exists:
                raise ValueError("That Position is already used in this category.")
            if tool_key == "complexion" and not data.title.strip():
                raise ValueError("Title is required for Complexion.")
        elif tool_key not in self.PRIVATE_TOOLS and (not data.title.strip() or not data.value.strip()):
            raise ValueError("Title and prompt value are required.")
        exists = db.query(ModelGenerationAsset).filter(
            ModelGenerationAsset.tool_key == tool_key,
            ModelGenerationAsset.asset_key == key,
        ).first()
        if exists:
            raise ValueError("An asset with that key already exists in this tool.")
        row = ModelGenerationAsset(
            tool_key=tool_key,
            asset_key=key,
            title=data.title.strip() if tool_key == "complexion" else ("" if tool_key in self.BODY_TOOLS else data.title.strip()),
            value="" if tool_key in self.BODY_TOOLS else data.value.strip(),
            sort_order=data.sort_order,
            position=data.position if tool_key in self.BODY_TOOLS else None,
            storage_mode=data.storage_mode,
            is_active=data.is_active,
            notes=data.notes,
            metadata_json=data.metadata,
        )
        db.add(row); db.commit(); db.refresh(row)
        return row

    def update(self, db: Session, asset_id: int, data: ModelGenerationAssetUpdate) -> ModelGenerationAsset:
        row = self.get(db, asset_id)
        patch = data.model_dump(exclude_unset=True)
        if "asset_key" in patch and patch["asset_key"] is not None:
            patch["asset_key"] = self._slug(patch["asset_key"])
            exists = db.query(ModelGenerationAsset).filter(
                ModelGenerationAsset.tool_key == row.tool_key,
                ModelGenerationAsset.asset_key == patch["asset_key"],
                ModelGenerationAsset.id != row.id,
            ).first()
            if exists:
                raise ValueError("An asset with that key already exists in this tool.")
        if "title" in patch and patch["title"] is not None:
            patch["title"] = patch["title"].strip()
        if "value" in patch and patch["value"] is not None:
            patch["value"] = patch["value"].strip()
        if "metadata" in patch:
            patch["metadata_json"] = patch.pop("metadata") or {}
        if row.tool_key in self.BODY_TOOLS:
            patch.pop("value", None)
            if row.tool_key != "complexion":
                patch.pop("title", None)
            if "position" in patch:
                if patch["position"] is None:
                    raise ValueError("Position is required for body preview assets.")
                position_exists = db.query(ModelGenerationAsset).filter(
                    ModelGenerationAsset.tool_key == row.tool_key,
                    ModelGenerationAsset.position == patch["position"],
                    ModelGenerationAsset.id != row.id,
                ).first()
                if position_exists:
                    raise ValueError("That Position is already used in this category.")
            if row.tool_key == "complexion" and "title" in patch and not (patch["title"] or "").strip():
                raise ValueError("Title is required for Complexion.")
        else:
            patch.pop("position", None)
        for key, value in patch.items():
            setattr(row, key, value)
        db.commit(); db.refresh(row)
        return row

    def _save(self, db: Session, *, mode: str, content: bytes, filename: str, content_type: str, folder: str) -> StorageFile:
        selected = storage_service.active_provider(db) if mode == "auto" else mode
        if selected == "local":
            return storage_service._save_local(
                db, user_id=None, content=content, original_filename=filename,
                content_type=content_type, folder=folder,
            )
        if selected in {StorageProvider.AMAZON_S3.value, StorageProvider.CLOUDFLARE_R2.value}:
            return storage_service._save_remote(
                db, provider=selected, user_id=None, content=content, original_filename=filename,
                content_type=content_type, folder=folder,
            )
        raise ValueError(f"Unsupported storage mode: {mode}")

    @staticmethod
    def _optimize_face_reference(content: bytes) -> tuple[bytes, str, str]:
        try:
            with Image.open(io.BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image = ImageOps.fit(image, (512, 720), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=95, method=6)
                return output.getvalue(), "face-reference.webp", "image/webp"
        except Exception as exc:
            raise ValueError("No se pudo procesar la imagen facial.") from exc

    def create_face_references(self, db: Session, *, files: list[tuple[bytes, str, str | None]], storage_mode: str) -> list[ModelGenerationAsset]:
        if storage_mode not in self.MODES:
            raise ValueError("Invalid storage target.")
        created: list[ModelGenerationAsset] = []
        base_order = db.query(ModelGenerationAsset).filter(ModelGenerationAsset.tool_key == "facial_structures").count() * 10
        for index, (content, filename, content_type) in enumerate(files, start=1):
            ctype = (content_type or "").split(";", 1)[0].strip().lower()
            if ctype not in self.IMAGE_TYPES:
                raise ValueError(f"Unsupported image content type: {ctype or 'unknown'}.")
            row = ModelGenerationAsset(
                tool_key="facial_structures", asset_key=f"face-{uuid4().hex}", title="", value="",
                sort_order=base_order + index * 10, position=None, storage_mode=storage_mode,
                is_active=True, notes=None, metadata_json={"source_filename": filename, "normalized_size": "512x720"},
            )
            db.add(row); db.commit(); db.refresh(row)
            self.upload_media(db, row.id, kind="poster", content=content, filename=filename, content_type=ctype)
            created.append(row)
        return created

    def upload_media(self, db: Session, asset_id: int, *, kind: str, content: bytes, filename: str, content_type: str | None) -> ModelGenerationAsset:
        row = self.get(db, asset_id)
        kind = kind.strip().lower()
        if kind not in {"poster", "video"}:
            raise ValueError("kind must be poster or video.")
        ctype = (content_type or "").split(";")[0].strip().lower()
        allowed = self.IMAGE_TYPES if kind == "poster" else self.VIDEO_TYPES
        if ctype not in allowed:
            raise ValueError(f"Unsupported {kind} content type: {ctype or 'unknown'}.")
        if row.tool_key == "facial_structures":
            if kind != "poster":
                raise ValueError("Facial structures only accept images.")
            content, filename, ctype = self._optimize_face_reference(content)
        stored = self._save(
            db,
            mode=row.storage_mode,
            content=content,
            filename=filename,
            content_type=ctype,
            folder=f"generation-tools/models-ia/{row.tool_key}/{row.asset_key}/{kind}",
        )
        attr = "poster_storage_file_id" if kind == "poster" else "video_storage_file_id"
        old = self._file(db, getattr(row, attr))
        setattr(row, attr, stored.id)
        db.commit(); db.refresh(row)
        if old and old.id != stored.id:
            try:
                storage_service.delete_file(db, storage_file=old)
                db.delete(old); db.commit()
            except Exception:
                db.rollback()
        return row

    def delete(self, db: Session, asset_id: int) -> None:
        row = self.get(db, asset_id)
        files = [self._file(db, row.poster_storage_file_id), self._file(db, row.video_storage_file_id)]
        db.delete(row); db.commit()
        for item in files:
            if not item:
                continue
            try:
                storage_service.delete_file(db, storage_file=item)
                db.delete(item); db.commit()
            except Exception:
                db.rollback()

    def export_zip(self, db: Session) -> bytes:
        payload = []
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
            for row in self.list(db):
                item = self.response(db, row)
                for field in ("poster_url", "video_url", "id", "created_at", "updated_at"):
                    item.pop(field, None)
                for kind, file_id in (("poster", row.poster_storage_file_id), ("video", row.video_storage_file_id)):
                    stored = self._file(db, file_id)
                    if not stored:
                        continue
                    ext = Path(stored.original_filename or stored.object_key).suffix or (".webp" if kind == "poster" else ".mp4")
                    arc = f"media/{row.tool_key}/{row.asset_key}/{kind}{ext}"
                    archive.writestr(arc, storage_service.read_bytes(db, storage_file=stored))
                    item[f"{kind}_archive_path"] = arc
                    item[f"{kind}_content_type"] = stored.content_type
                payload.append(item)
            archive.writestr("manifest.json", json.dumps({"version": 1, "items": payload}, indent=2, ensure_ascii=False))
        return memory.getvalue()

    def import_zip(self, db: Session, content: bytes, *, target: str = "auto") -> dict:
        if target not in self.MODES:
            raise ValueError("Invalid storage target.")
        created = updated = media = 0
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            manifest = json.loads(archive.read("manifest.json"))
            for item in manifest.get("items", []):
                raw_tool = item["tool_key"]
                if raw_tool not in self.TOOLS:
                    continue
                tool = self._canonical_tool(raw_tool)
                key = self._slug(item["asset_key"])
                row = db.query(ModelGenerationAsset).filter(
                    ModelGenerationAsset.tool_key == tool,
                    ModelGenerationAsset.asset_key == key,
                ).first()
                imported_position = item.get("position")
                if tool in self.BODY_TOOLS and imported_position is None:
                    current_positions = [
                        value for (value,) in db.query(ModelGenerationAsset.position)
                        .filter(ModelGenerationAsset.tool_key == tool, ModelGenerationAsset.position.isnot(None)).all()
                        if value is not None
                    ]
                    imported_position = (max(current_positions) if current_positions else 0) + 1
                common = {
                    "title": (item.get("title") or "").strip() if tool == "complexion" else ("" if tool in self.BODY_TOOLS else (item.get("title") or "").strip()),
                    "value": "" if tool in self.BODY_TOOLS else (item.get("value") or "").strip(),
                    "sort_order": item.get("sort_order", 100),
                    "position": imported_position if tool in self.BODY_TOOLS else None,
                    "storage_mode": target,
                    "is_active": item.get("is_active", True),
                    "notes": item.get("notes"),
                    "metadata_json": item.get("metadata") or {},
                }
                if row:
                    for k, v in common.items(): setattr(row, k, v)
                    updated += 1
                else:
                    row = ModelGenerationAsset(tool_key=tool, asset_key=key, **common)
                    db.add(row); created += 1
                db.commit(); db.refresh(row)
                for kind in ("poster", "video"):
                    arc = item.get(f"{kind}_archive_path")
                    if not arc:
                        continue
                    ctype = item.get(f"{kind}_content_type") or ("image/webp" if kind == "poster" else "video/mp4")
                    self.upload_media(
                        db, row.id, kind=kind, content=archive.read(arc),
                        filename=Path(arc).name, content_type=ctype,
                    )
                    media += 1
        return {"created": created, "updated": updated, "media_imported": media}


model_generation_asset_service = ModelGenerationAssetService()

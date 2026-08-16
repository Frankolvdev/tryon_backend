from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.common.enums import StorageProvider
from app.models.ancestry_media_asset import AncestryMediaAsset
from app.models.storage_file import StorageFile
from app.schemas.ancestry_media_asset import AncestryAssetCreate, AncestryAssetUpdate
from app.services.storage_service import storage_service


class AncestryMediaAssetService:
    MODES = ("auto", "local", "amazon_s3", "cloudflare_r2")
    VIDEO_TYPES = {"video/mp4", "video/webm"}
    IMAGE_TYPES = {"image/webp", "image/jpeg", "image/png"}

    @staticmethod
    def _slug(value: str) -> str:
        out = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        if not out:
            raise ValueError("Ancestry key is required.")
        return out

    def storage_options(self, db: Session) -> dict:
        return {"active_provider": storage_service.active_provider(db), "modes": list(self.MODES)}

    def list(self, db: Session, *, active_only: bool = False) -> list[AncestryMediaAsset]:
        q = db.query(AncestryMediaAsset)
        if active_only:
            q = q.filter(AncestryMediaAsset.is_active.is_(True))
        return q.order_by(AncestryMediaAsset.sort_order.asc(), AncestryMediaAsset.id.asc()).all()

    def get(self, db: Session, asset_id: int) -> AncestryMediaAsset:
        row = db.get(AncestryMediaAsset, asset_id)
        if not row:
            raise LookupError("Ancestry asset not found.")
        return row

    def _file(self, db: Session, file_id: int | None) -> StorageFile | None:
        return db.get(StorageFile, file_id) if file_id else None

    def response(self, db: Session, row: AncestryMediaAsset) -> dict:
        poster = self._file(db, row.poster_storage_file_id)
        video = self._file(db, row.video_storage_file_id)
        return {
            "id": row.id,
            "ancestry_key": row.ancestry_key,
            "display_name": row.display_name,
            "country_code": row.country_code,
            "flag_emoji": row.flag_emoji,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "sort_order": row.sort_order,
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

    def create(self, db: Session, data: AncestryAssetCreate) -> AncestryMediaAsset:
        key = self._slug(data.ancestry_key)
        if db.query(AncestryMediaAsset).filter(AncestryMediaAsset.ancestry_key == key).first():
            raise ValueError("An ancestry asset with that key already exists.")
        row = AncestryMediaAsset(
            ancestry_key=key,
            display_name=data.display_name.strip(),
            country_code=(data.country_code or "").upper() or None,
            flag_emoji=data.flag_emoji,
            latitude=data.latitude,
            longitude=data.longitude,
            sort_order=data.sort_order,
            storage_mode=data.storage_mode,
            is_active=data.is_active,
            notes=data.notes,
            metadata_json=data.metadata,
        )
        db.add(row); db.commit(); db.refresh(row)
        return row

    def update(self, db: Session, asset_id: int, data: AncestryAssetUpdate) -> AncestryMediaAsset:
        row = self.get(db, asset_id)
        patch = data.model_dump(exclude_unset=True)
        if "ancestry_key" in patch and patch["ancestry_key"] is not None:
            patch["ancestry_key"] = self._slug(patch["ancestry_key"])
            exists = db.query(AncestryMediaAsset).filter(
                AncestryMediaAsset.ancestry_key == patch["ancestry_key"],
                AncestryMediaAsset.id != row.id,
            ).first()
            if exists:
                raise ValueError("An ancestry asset with that key already exists.")
        if "country_code" in patch:
            patch["country_code"] = (patch["country_code"] or "").upper() or None
        if "metadata" in patch:
            patch["metadata_json"] = patch.pop("metadata") or {}
        for key, value in patch.items():
            setattr(row, key, value)
        db.commit(); db.refresh(row)
        return row

    def _save(self, db: Session, *, mode: str, content: bytes, filename: str, content_type: str, folder: str) -> StorageFile:
        selected = storage_service.active_provider(db) if mode == "auto" else mode
        if selected == "local":
            return storage_service._save_local(
                db, user_id=None, content=content, original_filename=filename,
                content_type=content_type, folder=folder
            )
        if selected in {StorageProvider.AMAZON_S3.value, StorageProvider.CLOUDFLARE_R2.value}:
            return storage_service._save_remote(
                db, provider=selected, user_id=None, content=content, original_filename=filename,
                content_type=content_type, folder=folder
            )
        raise ValueError(f"Unsupported storage mode: {mode}")

    def upload_media(self, db: Session, asset_id: int, *, kind: str, content: bytes, filename: str, content_type: str | None) -> AncestryMediaAsset:
        row = self.get(db, asset_id)
        kind = kind.strip().lower()
        if kind not in {"poster", "video"}:
            raise ValueError("kind must be poster or video.")
        ctype = (content_type or "").split(";")[0].strip().lower()
        allowed = self.IMAGE_TYPES if kind == "poster" else self.VIDEO_TYPES
        if ctype not in allowed:
            raise ValueError(f"Unsupported {kind} content type: {ctype or 'unknown'}.")
        stored = self._save(
            db, mode=row.storage_mode, content=content, filename=filename,
            content_type=ctype, folder=f"generation-tools/ancestry/{row.ancestry_key}/{kind}"
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
                item.pop("poster_url", None); item.pop("video_url", None)
                item.pop("id", None); item.pop("created_at", None); item.pop("updated_at", None)
                for kind, file_id in (("poster", row.poster_storage_file_id), ("video", row.video_storage_file_id)):
                    stored = self._file(db, file_id)
                    if not stored:
                        continue
                    ext = Path(stored.original_filename or stored.object_key).suffix or (".webp" if kind == "poster" else ".mp4")
                    arc = f"media/{row.ancestry_key}/{kind}{ext}"
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
                key = self._slug(item["ancestry_key"])
                row = db.query(AncestryMediaAsset).filter(AncestryMediaAsset.ancestry_key == key).first()
                common = {
                    "display_name": item["display_name"],
                    "country_code": item.get("country_code"),
                    "flag_emoji": item.get("flag_emoji"),
                    "latitude": item.get("latitude"),
                    "longitude": item.get("longitude"),
                    "sort_order": item.get("sort_order", 100),
                    "storage_mode": target,
                    "is_active": item.get("is_active", True),
                    "notes": item.get("notes"),
                    "metadata_json": item.get("metadata") or {},
                }
                if row:
                    for k, v in common.items(): setattr(row, k, v)
                    updated += 1
                else:
                    row = AncestryMediaAsset(ancestry_key=key, **common)
                    db.add(row); created += 1
                db.commit(); db.refresh(row)
                for kind in ("poster", "video"):
                    arc = item.get(f"{kind}_archive_path")
                    if not arc:
                        continue
                    ctype = item.get(f"{kind}_content_type") or ("image/webp" if kind == "poster" else "video/mp4")
                    row = self.upload_media(
                        db, row.id, kind=kind, content=archive.read(arc),
                        filename=Path(arc).name, content_type=ctype
                    )
                    media += 1
        return {"created": created, "updated": updated, "media_imported": media}


ancestry_media_asset_service = AncestryMediaAssetService()

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.common.enums import SettingCategory, SettingValueType
from app.models.storage_file import StorageFile
from app.repositories.system_setting_repository import system_setting_repository
from app.services.storage_service import storage_service


class BrandingService:
    """Provider-agnostic platform branding assets.

    The database only stores StorageFile ids. Every binary is persisted through
    StorageService, so changing LOCAL / S3 / R2 keeps the exact same routing
    rules as the rest of the platform. Public clients receive stable media
    endpoints instead of provider-specific signed URLs.
    """

    SETTING_KEY = "branding_assets_v1"
    MAX_UPLOAD_BYTES = 12 * 1024 * 1024
    LOGO_WIDTHS = {"small": 192, "medium": 384, "large": 768}
    FAVICON_SIZES = {"favicon_32": 32, "favicon_64": 64}
    ACCEPTED_TYPES = {"image/png", "image/jpeg", "image/webp"}

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "logo_original_file_id": None,
            "logo_small_file_id": None,
            "logo_medium_file_id": None,
            "logo_large_file_id": None,
            "favicon_auto_32_file_id": None,
            "favicon_auto_64_file_id": None,
            "favicon_custom_32_file_id": None,
            "favicon_custom_64_file_id": None,
            "favicon_mode": "auto",
            "version": 0,
        }

    def _setting(self, db: Session):
        return system_setting_repository.get_by_key(db, self.SETTING_KEY)

    def _read_config(self, db: Session) -> dict[str, Any]:
        row = self._setting(db)
        if not row or not row.value_json:
            return self._empty()
        try:
            payload = json.loads(row.value_json)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return {**self._empty(), **(payload if isinstance(payload, dict) else {})}

    def _write_config(self, db: Session, payload: dict[str, Any]) -> None:
        row = self._setting(db)
        encoded = json.dumps(payload, separators=(",", ":"))
        if row:
            row.value_json = encoded
            db.add(row)
            db.commit()
            return
        system_setting_repository.create(
            db,
            data={
                "category": SettingCategory.FRONTEND.value,
                "key": self.SETTING_KEY,
                "label": "Branding assets",
                "description": "Internal provider-agnostic file references for platform branding.",
                "value_type": SettingValueType.JSON.value,
                "value_json": encoded,
                "default_value_json": json.dumps(self._empty(), separators=(",", ":")),
                "is_public": False,
                "is_editable": False,
                "is_sensitive": False,
                "requires_restart": False,
                "sort_order": 5,
            },
        )

    @staticmethod
    def _open_image(content: bytes) -> Image.Image:
        try:
            image = Image.open(io.BytesIO(content))
            image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("El archivo no contiene una imagen válida.") from exc
        image = ImageOps.exif_transpose(image)
        if image.width < 8 or image.height < 8:
            raise ValueError("La imagen es demasiado pequeña.")
        if image.width * image.height > 50_000_000:
            raise ValueError("La imagen excede el tamaño máximo de procesamiento.")
        return image.convert("RGBA")

    def _validate_upload(self, content: bytes, content_type: str | None) -> None:
        if not content:
            raise ValueError("El archivo está vacío.")
        if len(content) > self.MAX_UPLOAD_BYTES:
            raise ValueError("El logotipo no puede superar 12 MB.")
        ctype = (content_type or "").split(";", 1)[0].strip().lower()
        if ctype and ctype not in self.ACCEPTED_TYPES:
            raise ValueError("Usa un archivo PNG, JPG o WEBP.")

    @staticmethod
    def _logo_variant(image: Image.Image, width: int) -> bytes:
        ratio = min(1.0, width / max(1, image.width))
        height = max(1, round(image.height * ratio))
        resized = image.resize((max(1, round(image.width * ratio)), height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        resized.save(output, format="WEBP", quality=88, method=6, lossless=False)
        return output.getvalue()

    @staticmethod
    def _favicon_variant(image: Image.Image, size: int) -> bytes:
        # Contain instead of crop: the automatic favicon never destroys the logo.
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        inner = max(1, round(size * 0.88))
        copy = image.copy()
        copy.thumbnail((inner, inner), Image.Resampling.LANCZOS)
        x = (size - copy.width) // 2
        y = (size - copy.height) // 2
        canvas.alpha_composite(copy, (x, y))
        output = io.BytesIO()
        canvas.save(output, format="PNG", optimize=True)
        return output.getvalue()

    def _save(self, db: Session, *, content: bytes, filename: str, content_type: str, folder: str) -> StorageFile:
        # This is intentionally the public StorageService entrypoint: active
        # provider selection remains centralized and historical files retain
        # the provider they were created with.
        return storage_service.save_bytes(
            db,
            user_id=None,
            content=content,
            original_filename=filename,
            content_type=content_type,
            folder=folder,
        )

    @staticmethod
    def _file(db: Session, file_id: int | None) -> StorageFile | None:
        return db.get(StorageFile, int(file_id)) if file_id else None

    def _cleanup_ids(self, db: Session, ids: list[int | None]) -> None:
        for file_id in {int(item) for item in ids if item}:
            stored = self._file(db, file_id)
            if not stored:
                continue
            try:
                storage_service.delete_file(db, storage_file=stored)
                db.delete(stored)
                db.commit()
            except Exception:
                db.rollback()

    def upload_logo(self, db: Session, *, content: bytes, filename: str, content_type: str | None) -> dict[str, Any]:
        self._validate_upload(content, content_type)
        image = self._open_image(content)
        old = self._read_config(db)
        created: list[StorageFile] = []
        try:
            suffix = Path(filename or "logo.png").suffix.lower() or ".png"
            original = self._save(
                db,
                content=content,
                filename=f"logo-original{suffix}",
                content_type=(content_type or "image/png").split(";", 1)[0],
                folder="platform-branding/logo/original",
            )
            created.append(original)
            variants: dict[str, StorageFile] = {}
            for key, width in self.LOGO_WIDTHS.items():
                stored = self._save(
                    db,
                    content=self._logo_variant(image, width),
                    filename=f"logo-{key}.webp",
                    content_type="image/webp",
                    folder=f"platform-branding/logo/{key}",
                )
                created.append(stored)
                variants[key] = stored
            auto: dict[str, StorageFile] = {}
            for key, size in self.FAVICON_SIZES.items():
                stored = self._save(
                    db,
                    content=self._favicon_variant(image, size),
                    filename=f"{key}.png",
                    content_type="image/png",
                    folder="platform-branding/favicon/auto",
                )
                created.append(stored)
                auto[key] = stored

            updated = {
                **old,
                "logo_original_file_id": original.id,
                "logo_small_file_id": variants["small"].id,
                "logo_medium_file_id": variants["medium"].id,
                "logo_large_file_id": variants["large"].id,
                "favicon_auto_32_file_id": auto["favicon_32"].id,
                "favicon_auto_64_file_id": auto["favicon_64"].id,
                "version": int(old.get("version") or 0) + 1,
            }
            self._write_config(db, updated)
            self._cleanup_ids(
                db,
                [
                    old.get("logo_original_file_id"), old.get("logo_small_file_id"),
                    old.get("logo_medium_file_id"), old.get("logo_large_file_id"),
                    old.get("favicon_auto_32_file_id"), old.get("favicon_auto_64_file_id"),
                ],
            )
            return self.response(db)
        except Exception:
            self._cleanup_ids(db, [item.id for item in created])
            raise

    def upload_favicon(self, db: Session, *, content: bytes, filename: str, content_type: str | None) -> dict[str, Any]:
        self._validate_upload(content, content_type)
        image = self._open_image(content)
        old = self._read_config(db)
        created: list[StorageFile] = []
        try:
            custom: dict[str, StorageFile] = {}
            for key, size in self.FAVICON_SIZES.items():
                stored = self._save(
                    db,
                    content=self._favicon_variant(image, size),
                    filename=f"custom-{key}.png",
                    content_type="image/png",
                    folder="platform-branding/favicon/custom",
                )
                created.append(stored)
                custom[key] = stored
            updated = {
                **old,
                "favicon_custom_32_file_id": custom["favicon_32"].id,
                "favicon_custom_64_file_id": custom["favicon_64"].id,
                "favicon_mode": "custom",
                "version": int(old.get("version") or 0) + 1,
            }
            self._write_config(db, updated)
            self._cleanup_ids(db, [old.get("favicon_custom_32_file_id"), old.get("favicon_custom_64_file_id")])
            return self.response(db)
        except Exception:
            self._cleanup_ids(db, [item.id for item in created])
            raise

    def set_app_name(self, db: Session, name: str) -> dict[str, Any]:
        clean = " ".join((name or "").strip().split())
        if not clean:
            raise ValueError("El nombre de la plataforma no puede estar vacío.")
        if len(clean) > 80:
            raise ValueError("El nombre de la plataforma no puede superar 80 caracteres.")
        row = system_setting_repository.get_by_key(db, "app_name")
        if row:
            row.value_string = clean
            db.add(row)
            db.commit()
        else:
            system_setting_repository.create(
                db,
                data={
                    "category": SettingCategory.GENERAL.value,
                    "key": "app_name",
                    "label": "Application Name",
                    "description": "Public application name.",
                    "value_type": SettingValueType.STRING.value,
                    "value_string": clean,
                    "default_value_string": clean,
                    "is_public": True,
                    "is_editable": True,
                    "is_sensitive": False,
                    "requires_restart": False,
                    "sort_order": 10,
                },
            )
        return self.response(db)

    def use_auto_favicon(self, db: Session) -> dict[str, Any]:
        current = self._read_config(db)
        current["favicon_mode"] = "auto"
        current["version"] = int(current.get("version") or 0) + 1
        self._write_config(db, current)
        return self.response(db)

    def response(self, db: Session) -> dict[str, Any]:
        config = self._read_config(db)
        app_name_setting = system_setting_repository.get_by_key(db, "app_name")
        app_name = (app_name_setting.value_string if app_name_setting else None) or "LUXIA"
        version = int(config.get("version") or 0)
        has_logo = bool(config.get("logo_small_file_id"))
        custom_available = bool(config.get("favicon_custom_64_file_id"))
        favicon_mode = "custom" if config.get("favicon_mode") == "custom" and custom_available else "auto"
        favicon_available = bool(
            config.get("favicon_custom_64_file_id") if favicon_mode == "custom" else config.get("favicon_auto_64_file_id")
        )
        suffix = f"?v={version}" if version else ""
        return {
            "app_name": app_name,
            "has_logo": has_logo,
            "logo": {
                "small_url": f"/api/v1/system/branding/assets/logo-small{suffix}" if has_logo else None,
                "medium_url": f"/api/v1/system/branding/assets/logo-medium{suffix}" if config.get("logo_medium_file_id") else None,
                "large_url": f"/api/v1/system/branding/assets/logo-large{suffix}" if config.get("logo_large_file_id") else None,
            },
            "favicon": {
                "mode": favicon_mode,
                "custom_available": custom_available,
                "url": f"/api/v1/system/branding/assets/favicon{suffix}" if favicon_available else None,
            },
            "active_storage_provider": storage_service.active_provider(db),
            "version": version,
        }

    def asset(self, db: Session, key: str) -> tuple[bytes, str, str]:
        config = self._read_config(db)
        mapping = {
            "logo-small": config.get("logo_small_file_id"),
            "logo-medium": config.get("logo_medium_file_id"),
            "logo-large": config.get("logo_large_file_id"),
        }
        if key == "favicon":
            if config.get("favicon_mode") == "custom" and config.get("favicon_custom_64_file_id"):
                file_id = config.get("favicon_custom_64_file_id")
            else:
                file_id = config.get("favicon_auto_64_file_id")
        else:
            file_id = mapping.get(key)
        stored = self._file(db, file_id)
        if not stored:
            raise ValueError("Branding asset not found.")
        content = storage_service.read_bytes(db, storage_file=stored)
        content_type = stored.content_type or ("image/png" if key == "favicon" else "image/webp")
        etag = hashlib.sha256(content).hexdigest()[:24]
        return content, content_type, etag


branding_service = BrandingService()

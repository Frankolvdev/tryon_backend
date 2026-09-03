import io
import json
import zipfile

from sqlalchemy.orm import Session

from app.services.ancestry_media_asset_service import ancestry_media_asset_service
from app.services.model_generation_asset_service import model_generation_asset_service


class ModelGenerationBundleService:
    def export_zip(self, db: Session) -> bytes:
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("ancestry-assets.zip", ancestry_media_asset_service.export_zip(db))
            archive.writestr("model-assets.zip", model_generation_asset_service.export_zip(db))
            archive.writestr(
                "bundle-manifest.json",
                json.dumps({"version": 1, "contents": ["ancestry-assets.zip", "model-assets.zip"]}, indent=2),
            )
        return memory.getvalue()

    def import_zip(self, db: Session, content: bytes, *, target: str = "auto") -> dict:
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            names = set(archive.namelist())
            if "ancestry-assets.zip" not in names or "model-assets.zip" not in names:
                raise ValueError("Invalid Models IA bundle.")
            ancestry = ancestry_media_asset_service.import_zip(db, archive.read("ancestry-assets.zip"), target=target)
            models = model_generation_asset_service.import_zip(db, archive.read("model-assets.zip"), target=target)
        return {"ancestry": ancestry, "models": models}


model_generation_bundle_service = ModelGenerationBundleService()

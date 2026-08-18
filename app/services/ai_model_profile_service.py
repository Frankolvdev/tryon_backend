import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_model_profile import AiModelProfile
from app.models.body_proportion_tool import BodyProportionPreset, BubbleButtPreset
from app.models.storage_file import StorageFile
from app.services.storage_service import storage_service
from app.services.body_proportion_tool_service import body_proportion_tool_service
from app.services.bubble_butt_tool_service import bubble_butt_tool_service


class AiModelProfileService:
    def _image_url(self, db: Session, preset: BodyProportionPreset | None) -> str | None:
        if not preset:
            return None
        stored = body_proportion_tool_service.preview_storage_file(db, preset)
        return storage_service.create_presigned_url(db, storage_file=stored) if stored else None

    def catalog(self, db: Session, sex: str) -> list[dict]:
        if sex not in {"woman", "man"}:
            raise ValueError("Invalid sex.")
        rows = list(db.execute(select(BodyProportionPreset).where(
            BodyProportionPreset.sex == sex,
            BodyProportionPreset.status == "ready",
        ).order_by(BodyProportionPreset.sort_order.asc(), BodyProportionPreset.id.asc())).scalars().all())
        result = []
        for row in rows:
            image_url = self._image_url(db, row)
            if not image_url:
                continue
            result.append({
                "id": row.id, "display_name": row.display_name, "sex": row.sex,
                "hips_size": row.hips_size, "fat_thin": row.fat_thin, "breasts_size": row.breasts_size,
                "skin_tone": row.skin_tone, "hair_length": row.hair_length,
                "fat_band": row.fat_band, "hips_band": row.ass_band, "breast_band": row.breast_band,
                "image_url": image_url, "sort_order": row.sort_order,
            })
        return result

    def bubble_variants_for_body(self, db: Session, preset_id: int) -> list[dict]:
        body = db.get(BodyProportionPreset, preset_id)
        if not body or body.status != "ready":
            raise LookupError("Body variant not found.")
        if not body.fat_band or not body.ass_band:
            return []

        rows = list(db.execute(select(BubbleButtPreset).where(
            BubbleButtPreset.sex == body.sex,
            BubbleButtPreset.fat_band == body.fat_band,
            BubbleButtPreset.ass_band == body.ass_band,
            BubbleButtPreset.status == "ready",
        ).order_by(BubbleButtPreset.variant_index.asc(), BubbleButtPreset.id.asc())).scalars().all())

        result = []
        for row in rows:
            stored = bubble_butt_tool_service.preview_storage_file(db, row)
            if not stored:
                continue
            image_url = storage_service.create_presigned_url(db, storage_file=stored)
            if image_url:
                result.append({
                    "id": row.id,
                    "variant_index": row.variant_index,
                    "display_name": row.display_name,
                    "bubble_butt": row.bubble_butt,
                    "image_url": image_url,
                })
        return result

    def list_models(self, db: Session, user_id: int) -> list[AiModelProfile]:
        return list(db.execute(select(AiModelProfile).where(AiModelProfile.user_id == user_id).order_by(AiModelProfile.updated_at.desc())).scalars().all())

    def get(self, db: Session, user_id: int, model_id: int) -> AiModelProfile:
        row = db.execute(select(AiModelProfile).where(AiModelProfile.id == model_id, AiModelProfile.user_id == user_id)).scalar_one_or_none()
        if not row:
            raise LookupError("AI model not found.")
        return row

    def create(self, db: Session, user_id: int, name: str, sex: str) -> AiModelProfile:
        if sex == "man":
            raise ValueError("Male model creation is prepared but not enabled yet.")
        row = AiModelProfile(user_id=user_id, name=name.strip(), sex=sex, stage="body")
        db.add(row); db.commit(); db.refresh(row); return row

    def set_body(
        self,
        db: Session,
        user_id: int,
        model_id: int,
        preset_id: int,
        bubble_butt_preset_id: int,
    ) -> AiModelProfile:
        row = self.get(db, user_id, model_id)
        preset = db.get(BodyProportionPreset, preset_id)
        if not preset or preset.sex != row.sex or preset.status != "ready" or not self._image_url(db, preset):
            raise ValueError("The selected body variant is not available from the active preview source.")

        bubble = db.get(BubbleButtPreset, bubble_butt_preset_id)
        if (
            not bubble
            or bubble.sex != row.sex
            or bubble.status != "ready"
            or bubble.fat_band != preset.fat_band
            or bubble.ass_band != preset.ass_band
            or bubble_butt_tool_service.preview_storage_file(db, bubble) is None
        ):
            raise ValueError("The selected Butt Elevation does not belong to the selected body or is not available.")

        row.body_proportion_preset_id = preset.id
        row.bubble_butt_preset_id = bubble.id
        row.stage = "body_selected"
        db.add(row); db.commit(); db.refresh(row); return row


    def save_draft(self, db: Session, user_id: int, model_id: int, draft: dict, name: str | None = None) -> AiModelProfile:
        row = self.get(db, user_id, model_id)
        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Model name cannot be empty.")
            duplicate = db.execute(select(AiModelProfile).where(
                AiModelProfile.user_id == user_id,
                AiModelProfile.name == clean_name,
                AiModelProfile.id != model_id,
            )).scalar_one_or_none()
            if duplicate:
                raise ValueError("You already have a model with that name.")
            row.name = clean_name
        safe_draft = dict(draft or {})
        if len(json.dumps(safe_draft, ensure_ascii=False)) > 65536:
            raise ValueError("Draft is too large.")
        row.draft_json = safe_draft
        db.add(row); db.commit(); db.refresh(row); return row

    def response(self, db: Session, row: AiModelProfile) -> dict:
        preset = db.get(BodyProportionPreset, row.body_proportion_preset_id) if row.body_proportion_preset_id else None
        bubble = db.get(BubbleButtPreset, row.bubble_butt_preset_id) if row.bubble_butt_preset_id else None
        return {
            "id": row.id, "name": row.name, "sex": row.sex,
            "body_proportion_preset_id": row.body_proportion_preset_id,
            "bubble_butt_preset_id": row.bubble_butt_preset_id,
            "bubble_butt_variant_index": bubble.variant_index if bubble else None,
            "body_image_url": self._image_url(db, preset), "stage": row.stage,
            "draft_json": row.draft_json or {},
            "created_at": row.created_at, "updated_at": row.updated_at,
        }

ai_model_profile_service = AiModelProfileService()

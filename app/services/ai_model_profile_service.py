import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_model_profile import AiModelProfile
from app.models.body_proportion_tool import BodyProportionPreset, BubbleButtPreset
from app.models.storage_file import StorageFile
from app.models.generation_module import GenerationModuleOutput
from app.services.storage_service import storage_service
from app.services.body_proportion_tool_service import body_proportion_tool_service
from app.services.bubble_butt_tool_service import bubble_butt_tool_service
from app.services.generation_module_execution_store_service import generation_module_execution_store_service
from app.services.generation_result_mime import is_generation_image


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

    def finalize(
        self,
        db: Session,
        user_id: int,
        model_id: int,
        execution_id,
        storage_file_id: int,
        primary_output_id: int | None = None,
        identity_face_storage_file_id: int | None = None,
        identity_face_output_id: int | None = None,
    ) -> AiModelProfile:
        row = self.get(db, user_id, model_id)

        execution = generation_module_execution_store_service.get(execution_id)
        if (
            execution is None
            or execution.user_id != user_id
            or execution.module_key != "create_model_woman"
            or execution.status != "completed"
        ):
            raise ValueError("The selected generation is not a completed Create Model Woman execution.")
        if execution.result_locked or execution.billing_access_status != "unlocked":
            raise ValueError("The selected generation result is not unlocked.")

        output_file_ids: set[int] = set()
        def collect_output_file_ids(value) -> None:
            if isinstance(value, dict):
                file_id = value.get("storage_file_id")
                if isinstance(file_id, int):
                    output_file_ids.add(file_id)
                for nested in value.values():
                    collect_output_file_ids(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect_output_file_ids(nested)

        collect_output_file_ids(execution.outputs)
        if storage_file_id not in output_file_ids:
            raise ValueError("The selected image does not belong to this generation execution.")

        def validate_bound_output(output_id: int, file_id: int, label: str) -> GenerationModuleOutput:
            output = db.get(GenerationModuleOutput, output_id)
            if not output or output.generation_module_id != execution.module_id:
                raise ValueError(f"The {label} output does not belong to this generation module.")
            if str(output.output_type or "").lower() not in {"image", "images"}:
                raise ValueError(f"The {label} output is not configured as an image output.")

            scoped_ids: set[int] = set()

            def collect_scoped(value) -> None:
                if isinstance(value, dict):
                    scoped_file_id = value.get("storage_file_id")
                    if isinstance(scoped_file_id, int):
                        scoped_ids.add(scoped_file_id)
                    for nested in value.values():
                        collect_scoped(nested)
                elif isinstance(value, list):
                    for nested in value:
                        collect_scoped(nested)

            collect_scoped((execution.outputs or {}).get(output.key))
            if file_id not in scoped_ids:
                raise ValueError(
                    f"The selected {label} image is not produced by module output {output.id} ({output.key})."
                )
            return output

        primary_output = None
        if primary_output_id is not None:
            primary_output = validate_bound_output(primary_output_id, storage_file_id, "primary model")

        stored = db.get(StorageFile, storage_file_id)
        if not stored or stored.user_id != user_id:
            raise LookupError("Generated image not found.")
        if not is_generation_image(stored.content_type, stored.original_filename):
            raise ValueError("The selected generation result is not an image.")

        if (identity_face_storage_file_id is None) != (identity_face_output_id is None):
            raise ValueError("Identity face file and output ID must be provided together.")

        identity_face = None
        identity_face_output = None
        if identity_face_storage_file_id is not None and identity_face_output_id is not None:
            identity_face_output = validate_bound_output(
                identity_face_output_id, identity_face_storage_file_id, "identity face"
            )
            if primary_output_id is not None and identity_face_output_id == primary_output_id:
                raise ValueError("Primary model image and identity face must use different outputs.")
            identity_face = db.get(StorageFile, identity_face_storage_file_id)
            if not identity_face or identity_face.user_id != user_id:
                raise LookupError("Generated identity face image not found.")
            if not is_generation_image(identity_face.content_type, identity_face.original_filename):
                raise ValueError("The identity face generation result is not an image.")

        draft = dict(row.draft_json or {})
        draft["selected_generation"] = {
            "execution_id": str(execution.id),
            "storage_file_id": stored.id,
            "primary_output_id": primary_output.id if primary_output else None,
            "primary_output_key": primary_output.key if primary_output else None,
            "identity_face_storage_file_id": identity_face.id if identity_face else None,
            "identity_face_output_id": identity_face_output.id if identity_face_output else None,
            "identity_face_output_key": identity_face_output.key if identity_face_output else None,
        }
        row.draft_json = draft
        row.stage = "studio"
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def delete(self, db: Session, user_id: int, model_id: int) -> None:
        row = self.get(db, user_id, model_id)
        db.delete(row)
        db.commit()

    def response(self, db: Session, row: AiModelProfile) -> dict:
        preset = db.get(BodyProportionPreset, row.body_proportion_preset_id) if row.body_proportion_preset_id else None
        bubble = db.get(BubbleButtPreset, row.bubble_butt_preset_id) if row.bubble_butt_preset_id else None
        selected_generation = dict(row.draft_json or {}).get("selected_generation") or {}
        selected_generation_file_id = selected_generation.get("storage_file_id")
        generated_image_url = None
        if selected_generation_file_id:
            stored = db.get(StorageFile, int(selected_generation_file_id))
            if stored and stored.user_id == row.user_id:
                generated_image_url = storage_service.create_presigned_url(db, storage_file=stored)

        return {
            "id": row.id, "name": row.name, "sex": row.sex,
            "body_proportion_preset_id": row.body_proportion_preset_id,
            "bubble_butt_preset_id": row.bubble_butt_preset_id,
            "bubble_butt_variant_index": bubble.variant_index if bubble else None,
            "body_image_url": self._image_url(db, preset),
            "generated_image_url": generated_image_url,
            "selected_generation_file_id": int(selected_generation_file_id) if selected_generation_file_id else None,
            "stage": row.stage,
            "draft_json": row.draft_json or {},
            "created_at": row.created_at, "updated_at": row.updated_at,
        }

ai_model_profile_service = AiModelProfileService()

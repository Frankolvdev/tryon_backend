import json
import os
import shutil
import subprocess

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting
from app.schemas.infrastructure_provider import ModalProviderConfig


class InfrastructureProviderService:
    KEY = "infrastructure_provider_modal"

    @classmethod
    def _get_row(cls, db: Session) -> SystemSetting | None:
        return db.query(SystemSetting).filter(SystemSetting.key == cls.KEY).first()

    @classmethod
    def get_modal(cls, db: Session) -> ModalProviderConfig:
        row = cls._get_row(db)
        if not row or not row.value_json:
            return ModalProviderConfig()
        try:
            return ModalProviderConfig.model_validate(json.loads(row.value_json))
        except Exception:
            return ModalProviderConfig()

    @classmethod
    def save_modal(cls, db: Session, payload: ModalProviderConfig) -> ModalProviderConfig:
        current = cls.get_modal(db)
        data = payload.model_dump()
        if not data.get("token_secret"):
            data["token_secret"] = current.token_secret
        row = cls._get_row(db)
        if row is None:
            row = SystemSetting(
                category="integrations",
                key=cls.KEY,
                label="Modal infrastructure provider",
                description="Modal provider configuration used by Runtime Builder and file tools.",
                value_type="json",
                is_public=False,
                is_editable=True,
                is_sensitive=True,
            )
        row.value_json = json.dumps(data, ensure_ascii=False)
        db.add(row)
        db.commit()
        db.refresh(row)
        return ModalProviderConfig.model_validate(data)

    @staticmethod
    def _modal_env(config: ModalProviderConfig) -> dict[str, str]:
        env = os.environ.copy()
        env["MODAL_TOKEN_ID"] = config.token_id
        env["MODAL_TOKEN_SECRET"] = config.token_secret
        env["MODAL_ENVIRONMENT"] = config.environment
        return env

    @classmethod
    def test_modal(cls, db: Session) -> dict:
        config = cls.get_modal(db)
        if not config.token_id or not config.token_secret:
            return {"success": False, "message": "Configura Token ID y Token Secret antes de probar la conexión.", "details": {}}
        executable = shutil.which("modal")
        if not executable:
            return {"success": False, "message": "Modal CLI no está instalado en el backend. Instala el paquete modal para probar y administrar volúmenes.", "details": {"required_command": "pip install modal"}}
        completed = subprocess.run(
            [executable, "profile", "current"],
            env=cls._modal_env(config), capture_output=True, text=True, timeout=30,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        return {
            "success": completed.returncode == 0,
            "message": "Conexión con Modal validada." if completed.returncode == 0 else "Modal rechazó la configuración.",
            "details": {"output": output[-2000:]},
        }

    @classmethod
    def ensure_volume(cls, db: Session) -> dict:
        config = cls.get_modal(db)
        if not config.token_id or not config.token_secret:
            return {"success": False, "message": "Configura las credenciales de Modal antes de crear el volumen.", "details": {}}
        executable = shutil.which("modal")
        if not executable:
            return {"success": False, "message": "Modal CLI no está instalado en el backend.", "details": {"required_command": "pip install modal"}}
        completed = subprocess.run(
            [executable, "volume", "create", config.volume_name],
            env=cls._modal_env(config), capture_output=True, text=True, timeout=60,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        benign = "already exists" in output.lower()
        success = completed.returncode == 0 or benign
        return {
            "success": success,
            "message": "Volumen Modal disponible." if success else "No fue posible crear o comprobar el volumen Modal.",
            "details": {"volume_name": config.volume_name, "output": output[-3000:]},
        }


infrastructure_provider_service = InfrastructureProviderService()

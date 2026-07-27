import json
import os
import shutil
import subprocess

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting
from app.schemas.infrastructure_provider import ModalProviderConfig, RunPodProviderConfig, BeamProviderConfig


class InfrastructureProviderService:
    KEY = "infrastructure_provider_modal"
    RUNPOD_KEY = "infrastructure_provider_runpod"
    BEAM_KEY = "infrastructure_provider_beam"

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

    @classmethod
    def _get_named_row(cls, db: Session, key: str) -> SystemSetting | None:
        return db.query(SystemSetting).filter(SystemSetting.key == key).first()

    @classmethod
    def _get_config(cls, db: Session, key: str, schema):
        row = cls._get_named_row(db, key)
        if not row or not row.value_json: return schema()
        try: return schema.model_validate(json.loads(row.value_json))
        except Exception: return schema()

    @classmethod
    def _save_config(cls, db: Session, key: str, label: str, payload, secret_field: str):
        current = cls._get_config(db, key, type(payload))
        data = payload.model_dump()
        if not data.get(secret_field): data[secret_field] = getattr(current, secret_field)
        row = cls._get_named_row(db, key) or SystemSetting(category="integrations", key=key, label=label, description=label, value_type="json", is_public=False, is_editable=True, is_sensitive=True)
        row.value_json = json.dumps(data, ensure_ascii=False); db.add(row); db.commit(); db.refresh(row)
        return type(payload).model_validate(data)

    @classmethod
    def get_runpod(cls, db: Session): return cls._get_config(db, cls.RUNPOD_KEY, RunPodProviderConfig)
    @classmethod
    def save_runpod(cls, db: Session, payload): return cls._save_config(db, cls.RUNPOD_KEY, "RunPod Serverless infrastructure provider", payload, "api_key")
    @classmethod
    def get_beam(cls, db: Session): return cls._get_config(db, cls.BEAM_KEY, BeamProviderConfig)
    @classmethod
    def save_beam(cls, db: Session, payload): return cls._save_config(db, cls.BEAM_KEY, "Beam infrastructure provider", payload, "api_key")

    @classmethod
    def test_runpod(cls, db: Session) -> dict:
        import urllib.request
        cfg=cls.get_runpod(db)
        if not cfg.api_key: return {"success":False,"message":"Configura la API key de RunPod.","details":{}}
        try:
            req=urllib.request.Request("https://api.runpod.io/graphql", data=b'{"query":"query { myself { id } }"}', headers={"Authorization":f"Bearer {cfg.api_key}","Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=20) as r: body=r.read().decode()
            return {"success":True,"message":"Conexión con RunPod validada.","details":{"response":body[-1000:]}}
        except Exception as exc: return {"success":False,"message":"RunPod rechazó la configuración.","details":{"error":str(exc)}}

    @classmethod
    def ensure_runpod_volume(cls, db: Session) -> dict:
        cfg=cls.get_runpod(db)
        if cfg.network_volume_id: return {"success":True,"message":"Volumen RunPod configurado.","details":{"volume_id":cfg.network_volume_id}}
        return {"success":False,"message":"RunPod requiere seleccionar o crear el volumen mediante su API; completa Network Volume ID.","details":{"volume_name":cfg.network_volume_name}}

    @classmethod
    def test_beam(cls, db: Session) -> dict:
        cfg=cls.get_beam(db)
        if not cfg.api_key: return {"success":False,"message":"Configura la API key de Beam.","details":{}}
        return {"success":True,"message":"Credenciales Beam guardadas; la prueba operativa se habilitará en MegaZIP C.","details":{"workspace":cfg.workspace}}

    @classmethod
    def ensure_beam_volume(cls, db: Session) -> dict:
        cfg=cls.get_beam(db)
        return {"success":bool(cfg.volume_name),"message":"Nombre de volumen Beam preparado." if cfg.volume_name else "Configura un volumen Beam.","details":{"volume_name":cfg.volume_name}}

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

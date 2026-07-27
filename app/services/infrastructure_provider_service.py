import json
import os
import shutil
import subprocess
import logging

from app.services.runpod_control_plane_service import runpod_control_plane_service

logger = logging.getLogger(__name__)

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
        cfg = cls.get_runpod(db)
        if not cfg.api_key:
            return {"success": False, "message": "Configura la API key de RunPod.", "details": {}}
        try:
            details = runpod_control_plane_service.account_probe(
                api_key=cfg.api_key,
                timeout_seconds=min(cfg.timeout_seconds, 60),
            )
            if cfg.endpoint_id:
                endpoint = runpod_control_plane_service.get_endpoint(
                    cfg.endpoint_id,
                    api_key=cfg.api_key,
                    timeout_seconds=min(cfg.timeout_seconds, 60),
                )
                details["endpoint"] = {
                    "id": endpoint.get("id"),
                    "name": endpoint.get("name"),
                    "workersMin": endpoint.get("workersMin"),
                    "workersMax": endpoint.get("workersMax"),
                }
            return {"success": True, "message": "Conexión con RunPod validada.", "details": details}
        except Exception as exc:
            return {"success": False, "message": "RunPod rechazó la configuración.", "details": {"error": str(exc)}}

    @classmethod
    def ensure_runpod_volume(cls, db: Session) -> dict:
        cfg = cls.get_runpod(db)
        if not cfg.api_key:
            return {"success": False, "message": "Configura la API key de RunPod.", "details": {}}

        timeout_seconds = min(cfg.timeout_seconds, 60)
        configured_id = str(cfg.network_volume_id or "").strip()
        stale_id_error: str | None = None

        try:
            # Un ID guardado puede quedar obsoleto, pertenecer a otra cuenta o haberse
            # copiado incorrectamente. Primero se intenta resolverlo, pero su fallo no
            # bloquea la búsqueda por nombre ni la creación del volumen.
            if configured_id:
                try:
                    volume = runpod_control_plane_service.get_network_volume(
                        configured_id,
                        api_key=cfg.api_key,
                        timeout_seconds=timeout_seconds,
                    )
                    return {
                        "success": True,
                        "message": "Network Volume de RunPod disponible.",
                        "details": volume,
                    }
                except Exception as exc:
                    stale_id_error = str(exc)
                    logger.warning(
                        "RunPod Network Volume ID no resoluble; se buscará por nombre: id=%s error=%s",
                        configured_id,
                        stale_id_error,
                    )

            volumes = runpod_control_plane_service.list_network_volumes(
                api_key=cfg.api_key,
                timeout_seconds=timeout_seconds,
            )
            wanted_name = str(cfg.network_volume_name or "").strip()
            wanted_dc = str(cfg.data_center_id or "").strip().upper()
            existing = next(
                (
                    item
                    for item in volumes
                    if str(item.get("name") or "").strip().casefold() == wanted_name.casefold()
                    and (
                        not wanted_dc
                        or str(item.get("dataCenterId") or "").strip().upper() == wanted_dc
                    )
                ),
                None,
            )
            if existing:
                cfg.network_volume_id = str(existing.get("id") or "").strip()
                cls.save_runpod(db, cfg)
                details = dict(existing)
                if stale_id_error:
                    details["replaced_stale_volume_id"] = configured_id
                    details["stale_volume_id_error"] = stale_id_error
                return {
                    "success": True,
                    "message": "Network Volume de RunPod encontrado y vinculado.",
                    "details": details,
                }

            if not wanted_name:
                return {
                    "success": False,
                    "message": "Configura el nombre del Network Volume.",
                    "details": {"stale_volume_id_error": stale_id_error},
                }
            if not wanted_dc:
                return {
                    "success": False,
                    "message": "Configura el Data Center ID para crear el Network Volume.",
                    "details": {
                        "volume_name": wanted_name,
                        "stale_volume_id_error": stale_id_error,
                    },
                }

            created = runpod_control_plane_service.create_network_volume(
                api_key=cfg.api_key,
                name=wanted_name,
                size_gb=cfg.network_volume_size_gb,
                data_center_id=wanted_dc,
                timeout_seconds=timeout_seconds,
            )
            created_id = str(created.get("id") or "").strip()
            if not created_id:
                raise RuntimeError(
                    f"RunPod creó el volumen pero no devolvió su ID: {created!r}"
                )
            cfg.network_volume_id = created_id
            cfg.data_center_id = wanted_dc
            cls.save_runpod(db, cfg)
            details = dict(created)
            if stale_id_error:
                details["replaced_stale_volume_id"] = configured_id
                details["stale_volume_id_error"] = stale_id_error
            return {
                "success": True,
                "message": "Network Volume de RunPod creado y vinculado.",
                "details": details,
            }
        except Exception as exc:
            logger.exception("No fue posible comprobar o crear el Network Volume de RunPod")
            return {
                "success": False,
                "message": (
                    "No fue posible comprobar o crear el Network Volume de RunPod. "
                    "Verifica que el Network Volume ID configurado exista y pertenezca a esta cuenta; "
                    "si ya no existe o no es correcto, elimina el ID y vuelve a intentarlo para crear o vincular un volumen nuevo."
                ),
                "details": {
                    "error": str(exc),
                    "configured_volume_id": configured_id or None,
                    "volume_name": str(cfg.network_volume_name or "").strip() or None,
                    "data_center_id": str(cfg.data_center_id or "").strip() or None,
                    "stale_volume_id_error": stale_id_error,
                },
            }

    @classmethod
    def test_beam(cls, db: Session) -> dict:
        import requests
        cfg=cls.get_beam(db)
        if not cfg.api_key: return {"success":False,"message":"Configura la API key de Beam.","details":{}}
        try:
            r=requests.get("https://api.beam.cloud/v2/task/00000000-0000-0000-0000-000000000000/",headers={"Authorization":f"Bearer {cfg.api_key}"},timeout=20)
            if r.status_code in {401,403}: return {"success":False,"message":"Beam rechazó la API key.","details":{"status_code":r.status_code}}
            return {"success":True,"message":"Credenciales Beam validadas.","details":{"workspace":cfg.workspace,"status_code":r.status_code}}
        except Exception as exc:
            return {"success":False,"message":"No fue posible conectar con Beam.","details":{"error":str(exc)}}

    @classmethod
    def ensure_beam_volume(cls, db: Session) -> dict:
        cfg=cls.get_beam(db)
        if not cfg.api_key: return {"success":False,"message":"Configura la API key de Beam.","details":{}}
        from app.services.beam_cli_environment_service import beam_cli_environment_service
        try:
            executable = beam_cli_environment_service.ensure(timeout_seconds=900)
        except Exception as exc:
            return {
                "success": False,
                "message": "No fue posible preparar el entorno aislado de Beam CLI.",
                "details": {"error": str(exc), "requirements": "requirements-beam.txt"},
            }
        import tempfile
        home=tempfile.mkdtemp(prefix="tryon-beam-")
        env=os.environ.copy(); env["HOME"]=home; env["USERPROFILE"]=home
        configured=subprocess.run([executable,"configure","default","--token",cfg.api_key],env=env,capture_output=True,text=True,timeout=30)
        if configured.returncode!=0:
            return {"success":False,"message":"Beam CLI rechazó la API key.","details":{"output":(configured.stdout or configured.stderr or "")[-3000:]}}
        listed=subprocess.run([executable,"volume","list"],env=env,capture_output=True,text=True,timeout=60)
        output=(listed.stdout or listed.stderr or "")
        if cfg.volume_name in output:
            return {"success":True,"message":"Volumen Beam disponible.","details":{"volume_name":cfg.volume_name,"output":output[-3000:]}}
        created=subprocess.run([executable,"volume","create",cfg.volume_name],env=env,capture_output=True,text=True,timeout=120)
        out=(created.stdout or created.stderr or "").strip()
        return {"success":created.returncode==0,"message":"Volumen Beam creado." if created.returncode==0 else "No fue posible crear el volumen Beam.","details":{"volume_name":cfg.volume_name,"output":out[-3000:]}}

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

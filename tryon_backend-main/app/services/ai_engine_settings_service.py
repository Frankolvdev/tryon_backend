from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.runpod_config import RunPodConfig
from app.models.system_setting import SystemSetting
from app.schemas.ai_engine_settings import AiEngineSettingsResponse, AiEngineSettingsUpdate


INTEGER_DEFAULTS = {
    "generation_local_parallel_executions": max(1, int(settings.GENERATION_LOCAL_WORKERS)),
    "runpod_min_workers": 0,
    "runpod_max_workers": 3,
    "generation_runpod_dispatch_workers": max(1, int(settings.GENERATION_RUNPOD_DISPATCH_WORKERS)),
    "generation_runpod_max_in_flight": max(1, int(getattr(settings, "GENERATION_RUNPOD_MAX_IN_FLIGHT", settings.GENERATION_RUNPOD_DISPATCH_WORKERS))),
    "modal_min_containers": 0,
    "modal_max_containers": 3,
    "modal_concurrency": 1,
    "modal_input_concurrency": 1000,
    "modal_scaledown_window_seconds": 300,
    "modal_execution_timeout_seconds": 1800,
    "generation_queue_block_seconds": max(1, int(settings.GENERATION_QUEUE_BLOCK_SECONDS)),
}
STRING_DEFAULTS = {"modal_gpu": "L40S"}
LABELS = {
    "modal_gpu": ("GPU de Modal", "GPU usada por los contenedores de Modal."),
    "modal_min_containers": ("Contenedores mínimos de Modal", "Contenedores calientes mínimos; 0 permite escalar a cero."),
    "modal_max_containers": ("Contenedores máximos de Modal", "Límite máximo de contenedores simultáneos."),
    "modal_concurrency": ("Workflows simultáneos por GPU", "Cantidad máxima de workflows pesados ejecutados simultáneamente por cada GPU."),
    "modal_input_concurrency": ("Conexiones HTTP/WebSocket por contenedor", "Entradas HTTP y WebSocket simultáneas por contenedor; no aumenta los workflows concurrentes ni el uso de VRAM."),
    "modal_scaledown_window_seconds": ("Ventana de apagado de Modal", "Segundos de inactividad antes de apagar un contenedor."),
    "modal_execution_timeout_seconds": ("Timeout de ejecución de Modal", "Tiempo máximo permitido por ejecución."),
}


class AiEngineSettingsService:
    def _integer_values(self, db: Session) -> dict[str, int]:
        rows = db.scalars(select(SystemSetting).where(SystemSetting.key.in_(INTEGER_DEFAULTS))).all()
        stored = {row.key: row.value_integer for row in rows}
        return {key: int(stored[key]) if stored.get(key) is not None else default for key, default in INTEGER_DEFAULTS.items()}

    def _string_values(self, db: Session) -> dict[str, str]:
        rows = db.scalars(select(SystemSetting).where(SystemSetting.key.in_(STRING_DEFAULTS))).all()
        stored = {row.key: row.value_string for row in rows}
        return {key: str(stored.get(key) or default) for key, default in STRING_DEFAULTS.items()}

    def get(self, db: Session) -> AiEngineSettingsResponse:
        v = self._integer_values(db); s = self._string_values(db)
        dispatchers=v["generation_runpod_dispatch_workers"]; in_flight=v["generation_runpod_max_in_flight"]
        return AiEngineSettingsResponse(
            local_parallel_executions=v["generation_local_parallel_executions"],
            runpod_min_workers=v["runpod_min_workers"], runpod_max_workers=v["runpod_max_workers"],
            runpod_dispatch_workers=dispatchers, runpod_max_in_flight=in_flight,
            modal_gpu=s["modal_gpu"], modal_min_containers=v["modal_min_containers"],
            modal_max_containers=v["modal_max_containers"], modal_concurrency=v["modal_concurrency"],
            modal_input_concurrency=v["modal_input_concurrency"],
            modal_scaledown_window_seconds=v["modal_scaledown_window_seconds"],
            modal_execution_timeout_seconds=v["modal_execution_timeout_seconds"],
            queue_block_seconds=v["generation_queue_block_seconds"],
            effective_runpod_parallelism=min(dispatchers,in_flight), requires_restart=True,
        )

    def update(self, db: Session, data: AiEngineSettingsUpdate) -> AiEngineSettingsResponse:
        incoming={
            "generation_local_parallel_executions":data.local_parallel_executions,
            "runpod_min_workers":data.runpod_min_workers,"runpod_max_workers":data.runpod_max_workers,
            "generation_runpod_dispatch_workers":data.runpod_dispatch_workers,
            "generation_runpod_max_in_flight":data.runpod_max_in_flight,
            "modal_min_containers":data.modal_min_containers,"modal_max_containers":data.modal_max_containers,
            "modal_concurrency":data.modal_concurrency,"modal_input_concurrency":data.modal_input_concurrency,
            "modal_scaledown_window_seconds":data.modal_scaledown_window_seconds,
            "modal_execution_timeout_seconds":data.modal_execution_timeout_seconds,
            "generation_queue_block_seconds":data.queue_block_seconds,
        }
        keys=list(incoming)+["modal_gpu"]
        existing={r.key:r for r in db.scalars(select(SystemSetting).where(SystemSetting.key.in_(keys))).all()}
        for order,(key,value) in enumerate(incoming.items(),start=10):
            row=existing.get(key)
            if row is None:
                label,desc=LABELS.get(key,(key,key))
                row=SystemSetting(category="ai",key=key,label=label,description=desc,value_type="integer",default_value_integer=INTEGER_DEFAULTS[key],is_public=False,is_editable=True,is_sensitive=False,requires_restart=True,sort_order=order)
            row.value_integer=value; db.add(row)
        row=existing.get("modal_gpu")
        if row is None:
            label,desc=LABELS["modal_gpu"]
            row=SystemSetting(category="ai",key="modal_gpu",label=label,description=desc,value_type="string",default_value_string="L40S",is_public=False,is_editable=True,is_sensitive=False,requires_restart=True,sort_order=60)
        row.value_string=data.modal_gpu; db.add(row)
        for config in db.scalars(select(RunPodConfig)).all():
            config.min_workers=data.runpod_min_workers; config.max_workers=data.runpod_max_workers
        db.commit(); return self.get(db)


ai_engine_settings_service=AiEngineSettingsService()

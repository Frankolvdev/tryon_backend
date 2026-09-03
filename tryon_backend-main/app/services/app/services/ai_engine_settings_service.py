from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.runpod_config import RunPodConfig
from app.models.system_setting import SystemSetting
from app.schemas.ai_engine_settings import AiEngineSettingsResponse, AiEngineSettingsUpdate


@dataclass(frozen=True)
class EngineSettingDefinition:
    key: str
    label: str
    description: str
    default: int
    sort_order: int


DEFINITIONS = (
    EngineSettingDefinition(
        key="generation_local_parallel_executions",
        label="Ejecuciones locales en paralelo",
        description="Cantidad máxima de ejecuciones locales que el backend procesa simultáneamente.",
        default=max(1, int(settings.GENERATION_LOCAL_WORKERS)),
        sort_order=10,
    ),
    EngineSettingDefinition(
        key="runpod_min_workers",
        label="Workers mínimos de RunPod",
        description="Cantidad mínima de workers remotos que RunPod debe mantener disponibles.",
        default=0,
        sort_order=20,
    ),
    EngineSettingDefinition(
        key="runpod_max_workers",
        label="Workers máximos de RunPod",
        description="Cantidad máxima de workers remotos que RunPod puede escalar para procesar trabajos.",
        default=3,
        sort_order=30,
    ),
    EngineSettingDefinition(
        key="generation_runpod_dispatch_workers",
        label="Dispatcher workers de RunPod",
        description="Cantidad de hilos del backend disponibles para despachar trabajos hacia RunPod.",
        default=max(1, int(settings.GENERATION_RUNPOD_DISPATCH_WORKERS)),
        sort_order=40,
    ),
    EngineSettingDefinition(
        key="generation_runpod_max_in_flight",
        label="Máximo de RunPod en vuelo",
        description="Límite total de trabajos RunPod que el backend puede mantener activos al mismo tiempo.",
        default=max(
            1,
            int(
                getattr(
                    settings,
                    "GENERATION_RUNPOD_MAX_IN_FLIGHT",
                    settings.GENERATION_RUNPOD_DISPATCH_WORKERS,
                )
            ),
        ),
        sort_order=50,
    ),
    EngineSettingDefinition(
        key="generation_queue_block_seconds",
        label="Espera de lectura de cola",
        description="Segundos que un worker espera por un nuevo trabajo antes de volver a consultar Redis.",
        default=max(1, int(settings.GENERATION_QUEUE_BLOCK_SECONDS)),
        sort_order=60,
    ),
)


class AiEngineSettingsService:
    def _get_values(self, db: Session) -> dict[str, int]:
        keys = [definition.key for definition in DEFINITIONS]
        rows = db.scalars(select(SystemSetting).where(SystemSetting.key.in_(keys))).all()
        stored = {row.key: row.value_integer for row in rows}
        return {
            definition.key: int(
                stored.get(definition.key)
                if stored.get(definition.key) is not None
                else definition.default
            )
            for definition in DEFINITIONS
        }

    def get(self, db: Session) -> AiEngineSettingsResponse:
        values = self._get_values(db)
        dispatchers = values["generation_runpod_dispatch_workers"]
        max_in_flight = values["generation_runpod_max_in_flight"]
        return AiEngineSettingsResponse(
            local_parallel_executions=values["generation_local_parallel_executions"],
            runpod_min_workers=values["runpod_min_workers"],
            runpod_max_workers=values["runpod_max_workers"],
            runpod_dispatch_workers=dispatchers,
            runpod_max_in_flight=max_in_flight,
            queue_block_seconds=values["generation_queue_block_seconds"],
            effective_runpod_parallelism=min(dispatchers, max_in_flight),
            requires_restart=True,
        )

    def update(self, db: Session, data: AiEngineSettingsUpdate) -> AiEngineSettingsResponse:
        incoming = {
            "generation_local_parallel_executions": data.local_parallel_executions,
            "runpod_min_workers": data.runpod_min_workers,
            "runpod_max_workers": data.runpod_max_workers,
            "generation_runpod_dispatch_workers": data.runpod_dispatch_workers,
            "generation_runpod_max_in_flight": data.runpod_max_in_flight,
            "generation_queue_block_seconds": data.queue_block_seconds,
        }
        existing = {
            row.key: row
            for row in db.scalars(
                select(SystemSetting).where(SystemSetting.key.in_(incoming.keys()))
            ).all()
        }
        for definition in DEFINITIONS:
            row = existing.get(definition.key)
            if row is None:
                row = SystemSetting(
                    category="ai",
                    key=definition.key,
                    label=definition.label,
                    description=definition.description,
                    value_type="integer",
                    default_value_integer=definition.default,
                    is_public=False,
                    is_editable=True,
                    is_sensitive=False,
                    requires_restart=True,
                    sort_order=definition.sort_order,
                )
                db.add(row)
            row.value_integer = incoming[definition.key]

        # La pestaña Motor IA es la única fuente administrativa para el escalado
        # remoto. Sincronizamos las configuraciones RunPod existentes para que la
        # pantalla RunPod pueda quedar limitada a conexión y despliegue.
        runpod_configs = db.scalars(select(RunPodConfig)).all()
        for config in runpod_configs:
            config.min_workers = data.runpod_min_workers
            config.max_workers = data.runpod_max_workers

        db.commit()
        return self.get(db)


ai_engine_settings_service = AiEngineSettingsService()

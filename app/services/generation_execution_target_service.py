from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from app.models.runtime_builder_build import RuntimeBuilderBuild
from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.services.docker_local_runtime_manager_service import docker_local_runtime_manager_service


class GenerationExecutionTargetService:
    """Read-only projection of Runtime Builder artifacts for Generation Modules.

    This service deliberately does not mutate builds, deployments, queues, billing,
    executions, provider configuration, or financial state.
    """

    @staticmethod
    def list_targets(db: Session) -> dict[str, list[dict[str, Any]]]:
        configs = {row.id: row for row in db.query(RuntimeBuilderConfig).all()}
        builds = db.query(RuntimeBuilderBuild).order_by(RuntimeBuilderBuild.id.desc()).all()
        result: dict[str, list[dict[str, Any]]] = {
            "modal": [], "runpod_serverless": [], "beam": [], "local_docker": []
        }
        seen: dict[str, set[str]] = {key: set() for key in result}

        def add(provider: str, value: str | None, *, label: str, build: RuntimeBuilderBuild, deployment_id: str | None = None, image_tag: str | None = None) -> None:
            value = str(value or "").strip()
            if not value or value in seen[provider]:
                return
            seen[provider].add(value)
            cfg = configs.get(build.runtime_config_id)
            result[provider].append({
                "provider": provider, "value": value, "label": label,
                "build_id": build.id, "deployment_id": deployment_id,
                "runtime_config_id": build.runtime_config_id,
                "runtime_name": getattr(cfg, "runtime_name", None),
                "version": build.version, "image_tag": image_tag or build.image_tag,
            })

        for build in builds:
            manifest = dict(build.manifest or {})
            for dep_id, raw in dict(manifest.get("deployments") or {}).items():
                dep = dict(raw or {})
                if str(dep.get("status") or "").lower() != "deployed":
                    continue
                provider = str(dep.get("provider") or "").lower()
                if provider == "modal":
                    value = dep.get("app_name")
                    add("modal", value, label=str(value or "Modal runtime"), build=build, deployment_id=str(dep_id), image_tag=dep.get("image_tag"))
                elif provider == "runpod":
                    value = dep.get("endpoint_id")
                    add("runpod_serverless", value, label=f"{dep.get('app_name') or 'RunPod'} · {value or ''}".strip(" ·"), build=build, deployment_id=str(dep_id), image_tag=dep.get("image_tag"))
                elif provider == "beam":
                    value = dep.get("endpoint")
                    add("beam", value, label=str(dep.get("app_name") or value or "Beam runtime"), build=build, deployment_id=str(dep_id), image_tag=dep.get("image_tag"))

            # Docker Local is a built image, not a deployed HTTP endpoint. Expose
            # it as a runtime choice only; the module keeps its explicit ComfyUI URL.
            if str(build.status or "").lower() in {"succeeded", "published", "active"} and build.image_tag:
                cfg = configs.get(build.runtime_config_id)
                runtime_name = getattr(cfg, "runtime_name", None) or build.image_tag
                add("local_docker", build.image_tag, label=f"{runtime_name}:{build.version}", build=build, image_tag=build.image_tag)
        return result


generation_execution_target_service = GenerationExecutionTargetService()

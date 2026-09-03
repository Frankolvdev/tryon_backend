import json, os, re, shlex, shutil, subprocess, threading, uuid
from pathlib import Path
from app.common.time import utc_now
from app.db.database import SessionLocal
from app.models.runtime_builder_build import RuntimeBuilderBuild
from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.models.runtime_project import RuntimeProject
from app.models.runpod_config import RunPodConfig
from app.services.runtime_builder_service import RuntimeBuilderService
from app.services.ai_engine_settings_service import ai_engine_settings_service

ROOT = Path(os.getenv("RUNTIME_BUILDS_DIR", "runtime_builds")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)

class RuntimeBuildExecutionService:
    @staticmethod
    def _runtime_modal_environment(db, build):
        """Return runtime-profile variables intended for the Modal launcher only.

        Runtime Builder profile variables are persisted separately from the global
        infrastructure provider.  Modal evaluates modal_app.py in the launcher
        process during deploy, so TRYON_MODAL_* switches must be present there.
        Keep the propagation deliberately scoped to this prefix; provider-owned
        deployment settings are applied afterwards and therefore remain authoritative.
        """
        config = db.get(RuntimeBuilderConfig, build.runtime_config_id)
        if config is None:
            return {}

        result = {}
        for item in getattr(config, "environment_variables", None) or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key.startswith("TRYON_MODAL_"):
                continue
            value = item.get("value")
            if value is None:
                continue
            result[key] = str(value)
        return result

    @staticmethod
    def _runtime_deployment_name(db, build, default_name):
        """Return the per-runtime deployment name, falling back to the provider default.

        The override is stored on RuntimeProject so provider credentials/configuration stay
        global while each exported runtime can choose its own deploy target name.
        """
        project = (
            db.query(RuntimeProject)
            .filter(RuntimeProject.runtime_config_id == build.runtime_config_id)
            .order_by(RuntimeProject.updated_at.desc(), RuntimeProject.id.desc())
            .first()
        )
        override = str(getattr(project, "deployment_name", None) or "").strip()
        return override or str(default_name or "").strip()

    @staticmethod
    def image_tag(config):
        base=config.registry_image.rstrip(":")
        safe_name = RuntimeBuilderService.sanitize_runtime_name(config.runtime_name)
        tag = ""
        if ":" in base.rsplit("/", 1)[-1]:
            base, tag = base.rsplit(":", 1)
        prefix = base.rsplit("/", 1)[0] if "/" in base else ""
        image = f"{prefix}/{safe_name}" if prefix else safe_name
        version = tag or config.runtime_version
        return f"{image}:{version}"

    @staticmethod
    def diagnostic(db):
        cfg=db.query(RuntimeBuilderConfig).order_by(RuntimeBuilderConfig.is_active.desc(), RuntimeBuilderConfig.id).first() or RuntimeBuilderConfig()
        try:
            result=subprocess.run(["docker","version","--format","{{.Server.Version}}"],capture_output=True,text=True,timeout=10)
            available=result.returncode==0
            version=result.stdout.strip() if available else None
        except Exception: available=False; version=None
        try:
            bx=subprocess.run(["docker","buildx","version"],capture_output=True,timeout=10).returncode==0
        except Exception: bx=False
        active=db.query(RuntimeBuilderBuild).filter(RuntimeBuilderBuild.active.is_(True)).order_by(RuntimeBuilderBuild.id.desc()).first()
        return {"docker_available":available,"docker_version":version,"buildx_available":bx,"registry_image":RuntimeBuildExecutionService.image_tag(cfg),"active_image":active.image_tag if active else None,"message":"Docker listo para construir." if available else "Docker no está disponible en el host del backend. También puedes ejecutar el build mediante CI usando el contexto generado."}

    @staticmethod
    def _resolve_context(db, config, requested_directory=None):
        candidates = []
        if requested_directory:
            candidates.append(requested_directory)

        projects = db.query(RuntimeProject).filter(
            (RuntimeProject.runtime_config_id == config.id) |
            (RuntimeProject.project_key == config.project_key)
        ).order_by(RuntimeProject.updated_at.desc(), RuntimeProject.id.desc()).all()
        for project in projects:
            if project.export_directory:
                candidates.append(project.export_directory)

        if config.export_directory:
            candidates.append(config.export_directory)
        if config.export_root_directory:
            candidates.append(str(Path(config.export_root_directory) / f"{config.project_key}-{config.runtime_version}"))

        seen = set()
        for raw in candidates:
            if not raw:
                continue
            normalized = os.path.normcase(os.path.abspath(os.path.expanduser(str(raw))))
            if normalized in seen:
                continue
            seen.add(normalized)
            path = Path(normalized)
            if path.exists() and path.is_dir():
                return path
        return None

    @staticmethod
    def _validate_context(path, config=None):
        # Estos son los nombres que genera RuntimeContextGeneratorService.
        # El Dockerfile utiliza scripts/startup.sh como ENTRYPOINT.
        required = [
            "Dockerfile",
            "manifest.json",
            "runtime.json",
            "requirements.txt",
            "scripts/startup.sh",
            "scripts/healthcheck.py",
        ]
        missing = [name for name in required if not (path / name).is_file()]
        if missing:
            raise ValueError(
                f"La exportación está incompleta o dañada en {path}. "
                f"Faltan: {', '.join(missing)}. Vuelve a generar el runtime autocontenido."
            )

        try:
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"manifest.json no es válido en {path}: {exc}") from exc

        try:
            runtime_manifest = json.loads((path / "runtime.json").read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"runtime.json no es válido en {path}: {exc}") from exc

        if manifest.get("contract") not in {"runtime-context/v3", "tryon.runtime-context/v2"}:
            raise ValueError(
                f"manifest.json no corresponde a un contexto Runtime Builder compatible en {path}."
            )

        # The generic Dockerfile must never contain Modal GPU Snapshot assets.
        # Older persisted exports may still contain them; reject those contexts
        # before invoking Docker so the user can regenerate with the current
        # generator. Dockerfile.modal is intentionally not affected.
        try:
            generic_dockerfile = (path / "Dockerfile").read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError as exc:
            raise ValueError(f"No se pudo leer Dockerfile en {path}: {exc}") from exc

        stale_modal_markers = (
            "modal-snapshot-warmup.json",
            "COPY runtime-engine.toml",
            "/opt/comfyui-runtime-engine",
        )
        if any(marker in generic_dockerfile for marker in stale_modal_markers):
            raise ValueError(
                "El contexto persistido usa un Dockerfile antiguo que contiene "
                "componentes exclusivos de Modal GPU Snapshot. Regenera el "
                "contexto reproducible antes de compilar; no es seguro reutilizarlo."
            )

        if config is not None:
            current_profile = RuntimeBuilderService.validated_profile_for_config(config)
            context_profile = runtime_manifest.get("compatibility_profile") or {}
            current_profile_id = (
                current_profile.get("id")
                if isinstance(current_profile, dict)
                else None
            )
            context_profile_id = (
                context_profile.get("id")
                if isinstance(context_profile, dict)
                else None
            )
            if (
                current_profile_id
                and context_profile_id
                and current_profile_id != context_profile_id
            ):
                raise ValueError(
                    "El contexto persistido fue generado con un perfil de "
                    f"compatibilidad distinto ({context_profile_id}) al perfil "
                    f"seleccionado actualmente ({current_profile_id}). "
                    "Regenera el contexto reproducible antes de compilar."
                )

        return {
            "valid": True,
            "context_path": str(path),
            "required_files": required,
            "manifest": manifest,
            "runtime_manifest": runtime_manifest,
        }

    @staticmethod
    def create(db, config, context_directory=None):
        validation=RuntimeBuilderService.validate(config)
        if not validation["valid"]: raise ValueError("La configuración contiene errores y no puede compilarse.")
        context = RuntimeBuildExecutionService._resolve_context(db, config, context_directory)
        if context is None:
            raise ValueError("No se encontró una exportación válida. Selecciona el directorio generado, por ejemplo ...\generation-runtime-1.0.0, antes de construir.")
        context_validation = RuntimeBuildExecutionService._validate_context(context, config)
        build=RuntimeBuilderBuild(
            runtime_config_id=config.id,
            version=config.runtime_version,
            image_tag=RuntimeBuildExecutionService.image_tag(config),
            context_path=str(context),
            manifest=context_validation["manifest"],
            validation_result={**validation, "context": context_validation},
            logs=f"[runtime-builder] Contexto validado antes de iniciar: {context}\n",
        )
        db.add(build); db.commit(); db.refresh(build); return build

    @staticmethod
    def start(build_id:int, push_after_build=False, no_cache=False):
        threading.Thread(target=RuntimeBuildExecutionService._run,args=(build_id,push_after_build,no_cache),daemon=True).start()

    @staticmethod
    def _append(db, build, line, phase=None, progress=None):
        build.logs=(build.logs or "") + line.rstrip() + "\n"
        if phase: build.phase=phase
        if progress is not None: build.progress=progress
        db.add(build); db.commit()

    @staticmethod
    def _run(build_id, push_after_build, no_cache=False):
        db=SessionLocal()
        try:
            build=db.get(RuntimeBuilderBuild,build_id); cfg=db.get(RuntimeBuilderConfig,build.runtime_config_id)
            build.status="building"; build.started_at=utc_now(); RuntimeBuildExecutionService._append(db,build,"[runtime-builder] Preparando contexto reproducible...","preparing",5)
            ctx = Path(build.context_path).expanduser().resolve() if build.context_path else RuntimeBuildExecutionService._resolve_context(db, cfg)
            if ctx is None:
                raise RuntimeError("No se encontró el directorio de exportación seleccionado para este build.")
            try:
                RuntimeBuildExecutionService._validate_context(ctx, cfg)
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            build.context_path=str(ctx)
            RuntimeBuildExecutionService._append(db,build,f"[runtime-builder] Usando exportación persistida: {ctx}","building",12)
            is_beam_build = str(getattr(cfg, "provider", "") or "").strip().lower() == "beam"
            if is_beam_build:
                # Beam builds only its provider-specific reusable image. This avoids
                # compiling the generic image first and then compiling Beam again.
                runtime_image = RuntimeBuildExecutionService._build_and_publish_beam_runtime_image(
                    db, build, cfg, ctx, no_cache=no_cache
                )
            else:
                runtime_image = build.image_tag
                cmd=['docker','build','--platform',cfg.target_platform,'-t',runtime_image,'-f',str(ctx/'Dockerfile')]
                if no_cache:
                    RuntimeBuildExecutionService._append(db,build,'[runtime-builder] Compilación sin caché activada: se ignorarán las layers anteriores.','building',12)
                    cmd.append('--no-cache')
                cmd.append(str(ctx))
                proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
                for line in proc.stdout or []:
                    db.refresh(build)
                    if build.status=='cancelled': proc.terminate(); return
                    RuntimeBuildExecutionService._append(db,build,line,"building",min(85,build.progress+1))
                if proc.wait()!=0: raise RuntimeError("docker build terminó con error.")

            inspect=subprocess.run(['docker','image','inspect',runtime_image,'--format','{{.Id}}|{{.Size}}'],capture_output=True,text=True,timeout=30)
            if inspect.returncode==0:
                parts=inspect.stdout.strip().split('|'); build.image_id=parts[0]; build.image_size_bytes=int(parts[1]) if len(parts)>1 else None
            build.status='validating'; RuntimeBuildExecutionService._append(db,build,"[runtime-builder] Imagen construida; validando metadatos...","validating",90)
            test=subprocess.run(['docker','run','--rm','--entrypoint','python3',runtime_image,'-c','import json; print("runtime-ok")'],capture_output=True,text=True,timeout=120)
            build.validation_result={**(build.validation_result or {}),"container_smoke_test":test.returncode==0,"smoke_output":(test.stdout+test.stderr)[-4000:],"validated_image":runtime_image}
            if test.returncode!=0: raise RuntimeError("La prueba de arranque del contenedor falló.")

            build.status='succeeded'; build.phase='completed'; build.progress=100; build.finished_at=utc_now(); RuntimeBuildExecutionService._append(db,build,"[runtime-builder] Build y validación completados.")
            if push_after_build and str(getattr(cfg, "provider", "") or "").strip().lower() != "beam":
                RuntimeBuildExecutionService.publish(build.id)
        except Exception as exc:
            build=db.get(RuntimeBuilderBuild,build_id)
            if build and build.status!='cancelled': build.status='failed'; build.phase='failed'; build.error_message=str(exc); build.finished_at=utc_now(); RuntimeBuildExecutionService._append(db,build,f"[error] {exc}")
        finally: db.close()

    @staticmethod
    def publish(build_id):
        db=SessionLocal()
        try:
            build=db.get(RuntimeBuilderBuild,build_id)
            if not build or build.status not in {'succeeded','published','active'}: raise ValueError('El build debe finalizar correctamente antes de publicarse.')
            build.status='publishing'; RuntimeBuildExecutionService._append(db,build,f"[runtime-builder] Publicando {build.image_tag}...","publishing",95)
            p=subprocess.run(['docker','push',build.image_tag],capture_output=True,text=True)
            RuntimeBuildExecutionService._append(db,build,p.stdout+p.stderr)
            if p.returncode: raise RuntimeError('docker push terminó con error. Inicia sesión en el registro en el host constructor.')
            build.published=True; build.status='published'; build.phase='published'; build.progress=100; db.add(build); db.commit()
        except Exception as exc:
            build=db.get(RuntimeBuilderBuild,build_id)
            if build: build.status='failed'; build.error_message=str(exc); RuntimeBuildExecutionService._append(db,build,f"[error] {exc}")
        finally: db.close()


    @staticmethod
    def deployment_providers(db):
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        modal = InfrastructureProviderService.get_modal(db)
        runpod = InfrastructureProviderService.get_runpod(db)
        beam = InfrastructureProviderService.get_beam(db)
        return [
            {
                "key": "modal",
                "label": "Modal",
                "enabled": bool(modal.enabled),
                "configured": bool(modal.token_id and modal.token_secret),
            },
            {
                "key": "runpod",
                "label": "RunPod Serverless",
                "enabled": bool(runpod.enabled),
                "configured": bool(runpod.api_key),
            },
            {
                "key": "beam",
                "label": "Beam",
                "enabled": bool(beam.enabled),
                "configured": bool(beam.api_key),
            },
        ]

    @staticmethod
    def _deployment_store(build):
        manifest = dict(build.manifest or {})
        deployments = dict(manifest.get("deployments") or {})
        return manifest, deployments

    @staticmethod
    def get_deployment(build, deployment_id):
        _, deployments = RuntimeBuildExecutionService._deployment_store(build)
        item = deployments.get(deployment_id)
        return dict(item) if item else None

    @staticmethod
    def _save_deployment(db, build, deployment):
        manifest, deployments = RuntimeBuildExecutionService._deployment_store(build)
        deployments[deployment["id"]] = dict(deployment)
        manifest["deployments"] = deployments
        manifest["latest_deployment_id"] = deployment["id"]
        build.manifest = manifest
        db.add(build)
        db.commit()
        db.refresh(build)
        return deployment

    @staticmethod
    def create_deployment(db, build, provider):
        if build.status not in {"succeeded", "published", "active"}:
            raise ValueError("La compilación debe finalizar correctamente antes de desplegarse.")
        providers = {item["key"]: item for item in RuntimeBuildExecutionService.deployment_providers(db)}
        selected = providers.get(provider)
        if not selected:
            raise ValueError("El proveedor seleccionado no está soportado.")
        if not selected["enabled"] or not selected["configured"]:
            raise ValueError(f"Configura y activa {selected['label']} en Proveedores de infraestructura.")
        now = utc_now().isoformat()
        deployment = {
            "id": uuid.uuid4().hex,
            "build_id": build.id,
            "provider": provider,
            "status": "queued",
            "phase": "queued",
            "progress": 0,
            "message": "Despliegue en cola.",
            "logs": "[deploy:0/6] Despliegue creado.\n",
            "error": None,
            "app_name": None,
            "image_tag": build.image_tag,
            "volume_name": None,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
        }
        return RuntimeBuildExecutionService._save_deployment(db, build, deployment)

    @staticmethod
    def _update_deployment(db, build, deployment, *, status=None, phase=None, progress=None, message=None, log=None, error=None, **extra):
        if status is not None:
            deployment["status"] = status
        if phase is not None:
            deployment["phase"] = phase
        if progress is not None:
            deployment["progress"] = progress
        if message is not None:
            deployment["message"] = message
        if error is not None:
            deployment["error"] = error
        if log:
            deployment["logs"] = (deployment.get("logs") or "") + log.rstrip() + "\n"
        deployment.update(extra)
        RuntimeBuildExecutionService._save_deployment(db, build, deployment)

    @staticmethod
    def _prepare_runpod_registry_image(build, cfg):
        """Resolve and validate the registry image used only by RunPod deployments.

        GHCR requires a real owner instead of the historical ``your-org`` placeholder.
        When GHCR_USERNAME is configured, the placeholder is replaced and the already
        built local image is retagged without rebuilding it.
        """
        image_tag = (build.image_tag or "").strip()
        if not image_tag:
            raise ValueError("La compilación no tiene una imagen Docker asignada.")

        if image_tag.startswith("ghcr.io/your-org/"):
            # GHCR/Docker exige que el propietario del repositorio esté en minúsculas.
            # Esta normalización pertenece exclusivamente al despliegue de RunPod.
            username = (cfg.ghcr_username or "").strip().lower()
            if not username:
                raise RuntimeError(
                    "El deploy de RunPod no puede publicar en ghcr.io/your-org: 'your-org' "
                    "es un valor provisional. Configura el usuario/organización y token de GHCR en el proveedor RunPod, o cambia 'Imagen del registro' por ghcr.io/<usuario>/<imagen>."
                )
            resolved_tag = "ghcr.io/" + username + "/" + image_tag[len("ghcr.io/your-org/"):]
            retag = subprocess.run(
                ["docker", "tag", image_tag, resolved_tag],
                capture_output=True, text=True, timeout=60,
            )
            if retag.returncode != 0:
                raise RuntimeError(
                    "No fue posible etiquetar la imagen para GHCR: "
                    + ((retag.stderr or retag.stdout or "error desconocido").strip())
                )
            build.image_tag = resolved_tag
            image_tag = resolved_tag

        return image_tag

    @staticmethod
    def _login_runpod_registry(image_tag, cfg):
        """Authenticate for the RunPod image registry without affecting other providers."""
        registry = image_tag.split("/", 1)[0] if "/" in image_tag else "docker.io"
        if registry != "ghcr.io":
            return None

        username = (cfg.ghcr_username or "").strip()
        token = (cfg.ghcr_token or "").strip()
        if not username or not token:
            # Docker may already be authenticated through its credential store. In that
            # case push is allowed to continue; any denial is converted to a precise error.
            return None

        login = subprocess.run(
            ["docker", "login", "ghcr.io", "-u", username, "--password-stdin"],
            input=token, capture_output=True, text=True, timeout=60,
        )
        if login.returncode != 0:
            raise RuntimeError(
                "No fue posible iniciar sesión en GHCR para el deploy de RunPod: "
                + ((login.stderr or login.stdout or "credenciales rechazadas").strip())
            )
        return "Autenticación GHCR validada para RunPod."

    @staticmethod
    def _runpod_deployment(db, build, deployment):
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        from app.services.runpod_control_plane_service import runpod_control_plane_service

        cfg = InfrastructureProviderService.get_runpod(db)
        if not cfg.enabled or not cfg.api_key:
            raise ValueError("Activa RunPod y configura su API key en Proveedores de infraestructura.")
        deployment_name = RuntimeBuildExecutionService._runtime_deployment_name(
            db, build, cfg.endpoint_name
        )
        if not deployment_name:
            raise ValueError("Configura un nombre de despliegue para RunPod.")
        image_tag = RuntimeBuildExecutionService._prepare_runpod_registry_image(build, cfg)
        login_message = RuntimeBuildExecutionService._login_runpod_registry(image_tag, cfg)
        db.add(build)
        db.commit()

        RuntimeBuildExecutionService._update_deployment(
            db, build, deployment,
            phase="publishing-image", progress=25,
            message="Publicando imagen Docker.",
            log=(
                (f"[runpod:auth] {login_message}\n" if login_message else "")
                + f"[runpod:2/6] Publicando {image_tag} en el registro."
            ),
            image_tag=image_tag,
            app_name=deployment_name,
            volume_name=cfg.network_volume_name,
        )
        if not build.published:
            pushed = subprocess.run(["docker", "push", image_tag], capture_output=True, text=True)
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                log=(pushed.stdout or "") + (pushed.stderr or ""),
            )
            if pushed.returncode != 0:
                output = ((pushed.stderr or "") + "\n" + (pushed.stdout or "")).strip()
                if "denied" in output.lower() or "unauthorized" in output.lower():
                    raise RuntimeError(
                        "GHCR rechazó la publicación del deploy de RunPod. Verifica que "
                        "el usuario/organización GHCR del proveedor RunPod corresponda al propietario de la imagen y que el token tenga permiso write:packages. Imagen: " + image_tag
                    )
                raise RuntimeError("docker push terminó con error: " + (output[-1200:] or "error desconocido"))
            build.published = True
            db.add(build)
            db.commit()

        RuntimeBuildExecutionService._update_deployment(
            db, build, deployment,
            phase="preparing-template", progress=45,
            message="Creando plantilla Serverless.",
            log="[runpod:3/6] Comprobando plantilla RunPod.",
        )
        template_id = cfg.template_id.strip()
        if template_id:
            runpod_control_plane_service.request(
                "GET", f"templates/{template_id}", api_key=cfg.api_key,
                timeout_seconds=min(cfg.timeout_seconds, 90),
            )
        else:
            # Cada build crea una plantilla inmutable. El endpoint se actualiza a la
            # plantilla nueva mediante rolling release, evitando reutilizar una imagen vieja.
            versioned_template_name = f"{cfg.template_name}-{build.id}"
            template = runpod_control_plane_service.find_template_by_name(
                versioned_template_name,
                api_key=cfg.api_key,
                timeout_seconds=min(cfg.timeout_seconds, 90),
            )
            if not template:
                template = runpod_control_plane_service.create_template(
                    api_key=cfg.api_key,
                    name=versioned_template_name,
                    image_name=build.image_tag,
                    container_disk_gb=cfg.container_disk_gb,
                    registry_auth_id=cfg.registry_auth_id or None,
                    env={"RUNTIME_PROVIDER": "runpod", "PYTHONUNBUFFERED": "1"},
                    timeout_seconds=min(cfg.timeout_seconds, 90),
                )
            template_id = str(template.get("id") or "")
            if not template_id:
                raise RuntimeError("RunPod no devolvió el ID de la plantilla.")

        RuntimeBuildExecutionService._update_deployment(
            db, build, deployment,
            phase="deploying-endpoint", progress=68,
            message="Creando o actualizando endpoint Serverless.",
            log=f"[runpod:4/6] Plantilla lista: {template_id}.",
        )
        if cfg.workers_min > cfg.workers_max:
            raise ValueError("RunPod requiere workersMin menor o igual que workersMax.")

        endpoint_payload = {
            "templateId": template_id,
            "computeType": "GPU",
            "executionTimeoutMs": int(cfg.execution_timeout_seconds) * 1000,
            "flashboot": bool(cfg.flashboot),
            "gpuCount": 1,
            "gpuTypeIds": [str(value).strip() for value in cfg.gpu_type_ids if str(value).strip()],
            "idleTimeout": int(cfg.idle_timeout_seconds),
            "name": deployment_name,
            "scalerType": str(cfg.scaler_type).strip(),
            "scalerValue": int(cfg.scaler_value),
            "workersMax": int(cfg.workers_max),
            "workersMin": int(cfg.workers_min),
        }
        allowed_cuda_versions = [
            str(value).strip() for value in cfg.allowed_cuda_versions if str(value).strip()
        ]
        if allowed_cuda_versions:
            endpoint_payload["allowedCudaVersions"] = allowed_cuda_versions

        configured_data_center = str(cfg.data_center_id or "").strip()
        network_volume_id = str(cfg.network_volume_id or "").strip()
        if network_volume_id:
            # A RunPod network volume belongs to exactly one datacenter. Sending a
            # different datacenter (or both singular/plural volume fields) can make
            # endpoint creation fail with an opaque HTTP 500. Resolve the authoritative
            # datacenter from RunPod and send only the documented single-volume field.
            volume = runpod_control_plane_service.get_network_volume(
                network_volume_id,
                api_key=cfg.api_key,
                timeout_seconds=min(cfg.timeout_seconds, 90),
            )
            volume_data_center = str(volume.get("dataCenterId") or "").strip()
            if configured_data_center and volume_data_center and configured_data_center != volume_data_center:
                raise ValueError(
                    "El volumen RunPod y el centro de datos configurado no coinciden: "
                    f"volumen={volume_data_center}, configuración={configured_data_center}."
                )
            endpoint_payload["networkVolumeId"] = network_volume_id
            if volume_data_center:
                endpoint_payload["dataCenterIds"] = [volume_data_center]
        elif configured_data_center:
            endpoint_payload["dataCenterIds"] = [configured_data_center]

        timeout_seconds = min(cfg.timeout_seconds, 120)
        endpoint = None
        provider_default_name = str(cfg.endpoint_name or "").strip()
        uses_provider_default = deployment_name == provider_default_name
        endpoint_id = str(cfg.endpoint_id or "").strip() if uses_provider_default else ""

        # Recover an endpoint created by a previous attempt before creating another one.
        if not endpoint_id:
            existing = runpod_control_plane_service.find_endpoint_by_name(
                endpoint_payload["name"],
                api_key=cfg.api_key,
                timeout_seconds=min(cfg.timeout_seconds, 90),
            )
            endpoint_id = str((existing or {}).get("id") or "").strip()
            if endpoint_id and uses_provider_default:
                cfg.endpoint_id = endpoint_id
                InfrastructureProviderService.save_runpod(db, cfg)

        if endpoint_id:
            endpoint = runpod_control_plane_service.update_endpoint(
                endpoint_id,
                api_key=cfg.api_key,
                payload=endpoint_payload,
                timeout_seconds=timeout_seconds,
            )
        else:
            try:
                endpoint = runpod_control_plane_service.create_endpoint(
                    api_key=cfg.api_key,
                    payload=endpoint_payload,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as first_error:
                # Some RunPod control-plane failures return HTTP 500 for an optional
                # setting rather than a validation response. Create the endpoint using
                # the smallest documented contract, persist its ID, then apply the full
                # configuration through PATCH. This fallback is RunPod-only.
                minimal_payload = {
                    "templateId": template_id,
                    "name": endpoint_payload["name"],
                    "computeType": "GPU",
                }
                try:
                    endpoint = runpod_control_plane_service.create_endpoint(
                        api_key=cfg.api_key,
                        payload=minimal_payload,
                        timeout_seconds=timeout_seconds,
                    )
                except Exception as fallback_error:
                    raise RuntimeError(
                        "RunPod no pudo crear el endpoint ni con el contrato completo ni "
                        "con el contrato mínimo. Error completo: " + str(first_error)
                        + " | Error mínimo: " + str(fallback_error)
                    ) from fallback_error

                endpoint_id = str(endpoint.get("id") or "").strip()
                if not endpoint_id:
                    raise RuntimeError("RunPod creó una respuesta sin ID de endpoint.")
                if uses_provider_default:
                    cfg.endpoint_id = endpoint_id
                    InfrastructureProviderService.save_runpod(db, cfg)
                endpoint = runpod_control_plane_service.update_endpoint(
                    endpoint_id,
                    api_key=cfg.api_key,
                    payload=endpoint_payload,
                    timeout_seconds=timeout_seconds,
                )

            if uses_provider_default:
                cfg.endpoint_id = str(endpoint.get("id") or "").strip()
                InfrastructureProviderService.save_runpod(db, cfg)

        endpoint_id = str(endpoint.get("id") or (cfg.endpoint_id if uses_provider_default else "") or "")
        if not endpoint_id:
            raise RuntimeError("RunPod no devolvió el ID del endpoint.")
        RuntimeBuildExecutionService._update_deployment(
            db, build, deployment,
            phase="verifying-deployment", progress=92,
            message="Verificando endpoint RunPod.",
            log=f"[runpod:5/6] Endpoint disponible: {endpoint_id}.",
            endpoint_id=endpoint_id,
            template_id=template_id,
        )
        verified = runpod_control_plane_service.get_endpoint(
            endpoint_id,
            api_key=cfg.api_key,
            timeout_seconds=min(cfg.timeout_seconds, 90),
        )
        deployment["finished_at"] = utc_now().isoformat()
        RuntimeBuildExecutionService._update_deployment(
            db, build, deployment,
            status="deployed", phase="completed", progress=100,
            message="Despliegue RunPod completado.",
            log="[runpod:6/6] Plantilla y endpoint creados o actualizados correctamente.",
            endpoint_id=endpoint_id,
            endpoint_name=verified.get("name"),
            template_id=template_id,
        )


    @staticmethod
    def _beam_runtime_fingerprint(source_context):
        """Return a content fingerprint for the Beam runtime only.

        Provider configuration (GPU, keep-warm, workers, checkpoint, etc.) is
        deliberately excluded. Modal and RunPod do not call this helper.
        """
        import hashlib

        source_context = Path(source_context).resolve()
        digest = hashlib.sha256()
        excluded_dirs = {
            ".git", ".github", ".pytest_cache", ".mypy_cache", ".ruff_cache",
            "__pycache__", "tests", "test", "docs", "examples", "example",
            "demo", "demos",
        }
        excluded_suffixes = {".pyc", ".pyo"}

        for candidate in sorted(source_context.rglob("*")):
            try:
                relative = candidate.relative_to(source_context)
            except ValueError:
                continue
            lowered = tuple(part.lower() for part in relative.parts)
            if any(
                part in excluded_dirs
                or (part.startswith("blender-") and "windows-x64" in part)
                for part in lowered
            ):
                continue
            if any(
                len(lowered) >= 2 and lowered[-2:] == pair
                for pair in (
                    ("assets", "videos"), ("assets", "video"),
                    ("assets", "demos"), ("assets", "demo"),
                    ("assets", "examples"), ("assets", "example"),
                )
            ):
                continue
            if not candidate.is_file() or candidate.suffix.lower() in excluded_suffixes:
                continue
            digest.update(relative.as_posix().encode("utf-8", errors="surrogatepass"))
            digest.update(b"\0")
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _beam_immutable_image_ref(build, fingerprint):
        image_tag = str(build.image_tag or "").strip()
        if not image_tag:
            raise ValueError("El build no tiene una etiqueta Docker configurada.")
        if image_tag.startswith("ghcr.io/your-org/"):
            raise ValueError(
                "La imagen configurada todavía usa ghcr.io/your-org. Cambia Imagen del registro "
                "en Runtime Builder por un repositorio real antes de preparar la imagen Beam."
            )
        last = image_tag.rsplit("/", 1)[-1]
        repository = image_tag.rsplit(":", 1)[0] if ":" in last else image_tag
        return f"{repository}:beam-{str(fingerprint)[:20]}"

    @staticmethod
    def _ensure_beam_registry_image(db, build, source_context, deployment):
        """Build and publish an immutable, Beam-only image for this runtime hash.

        This path never changes the shared Dockerfile used by Modal or RunPod.
        The first Beam image is built from a provider-specific context. Later
        runtime changes reuse Docker layers and rebuild only affected node layers.
        Configuration-only deploys reuse the already published image directly.
        """
        fingerprint = RuntimeBuildExecutionService._beam_runtime_fingerprint(source_context)
        manifest = dict(build.manifest or {})
        binding = dict(manifest.get("beam_runtime_image") or {})
        if (
            str(binding.get("fingerprint") or "") == fingerprint
            and str(binding.get("image_ref") or "").strip()
            and bool(binding.get("published"))
        ):
            return str(binding["image_ref"]).strip(), fingerprint, False

        image_ref = RuntimeBuildExecutionService._beam_immutable_image_ref(build, fingerprint)
        deploy_root = None
        try:
            deploy_root, context, excluded, reused = (
                RuntimeBuildExecutionService._prepare_beam_deploy_context(source_context)
            )
            dockerfile = context / "Dockerfile"
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                phase="building-runtime-image", progress=25,
                message="Construyendo imagen incremental exclusiva de Beam.",
                log=(
                    f"[beam:image] Imagen inmutable: {image_ref}.\n"
                    f"[beam:image] Contexto Beam {'reutilizado' if reused else 'preparado'}; "
                    f"se excluyeron {excluded['directories']} directorios y {excluded['files']} archivos.\n"
                    "[beam:image] Modal y RunPod no usan este Dockerfile ni este contexto."
                ),
            )
            command = [
                "docker", "build", "--platform", "linux/amd64",
                "-t", image_ref, "-f", str(dockerfile), str(context),
            ]
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in process.stdout or []:
                RuntimeBuildExecutionService._update_deployment(
                    db, build, deployment, log="[beam:image] " + line.rstrip()
                )
            if process.wait() != 0:
                raise RuntimeError(
                    "No fue posible construir la imagen incremental de Beam. "
                    "Las imágenes y flujos de Modal/RunPod no fueron modificados."
                )

            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                phase="publishing-runtime-image", progress=38,
                message="Publicando imagen inmutable de Beam.",
                log=f"[beam:image] Publicando {image_ref} en el registro configurado.",
            )
            pushed = subprocess.Popen(
                ["docker", "push", image_ref],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in pushed.stdout or []:
                RuntimeBuildExecutionService._update_deployment(
                    db, build, deployment, log="[beam:image] " + line.rstrip()
                )
            if pushed.wait() != 0:
                raise RuntimeError(
                    "No fue posible publicar la imagen inmutable de Beam. Ejecuta "
                    "docker login para el registro configurado y verifica permisos de escritura."
                )
        finally:
            # The persistent Beam context is intentionally retained for Docker layer
            # reuse. Only temporary derivative directories would be removed here.
            pass

        manifest["beam_runtime_image"] = {
            "fingerprint": fingerprint,
            "image_ref": image_ref,
            "published": True,
            "published_at": utc_now().isoformat(),
            "source": "beam_incremental_registry_image",
        }
        build.manifest = manifest
        db.add(build)
        db.commit()
        db.refresh(build)
        return image_ref, fingerprint, True

    @staticmethod
    def _build_and_publish_beam_runtime_image(db, build, cfg, source_context, no_cache=False):
        """Builds and publishes the reusable Beam image during Build only.

        This method is intentionally called only from the explicit Runtime Builder
        Build action when the runtime configuration provider is ``beam``. It never
        runs from Deploy, Modal or RunPod.
        """
        fingerprint = RuntimeBuildExecutionService._beam_runtime_fingerprint(source_context)
        image_ref = RuntimeBuildExecutionService._beam_immutable_image_ref(build, fingerprint)
        manifest = dict(build.manifest or {})
        existing = dict(manifest.get("beam_runtime_image") or {})

        if (
            str(existing.get("fingerprint") or "") == fingerprint
            and str(existing.get("image_ref") or "").strip() == image_ref
            and bool(existing.get("published"))
        ):
            RuntimeBuildExecutionService._append(
                db, build,
                f"[beam-build] Imagen reutilizable ya preparada: {image_ref}",
                "beam-image-ready", 96,
            )
            return image_ref

        RuntimeBuildExecutionService._append(
            db, build,
            f"[beam-build] Preparando imagen reutilizable por huella: {image_ref}",
            "beam-image-preparing", 92,
        )
        deploy_root, context, excluded, reused = (
            RuntimeBuildExecutionService._prepare_beam_deploy_context(source_context)
        )
        dockerfile = context / "Dockerfile"
        RuntimeBuildExecutionService._append(
            db, build,
            "[beam-build] Contexto exclusivo de Beam "
            + ("reutilizado" if reused else "preparado")
            + f"; excluidos {excluded['directories']} directorios y {excluded['files']} archivos.",
            "beam-image-building", 93,
        )

        command = [
            "docker", "build", "--platform", str(cfg.target_platform or "linux/amd64"),
            "-t", image_ref, "-f", str(dockerfile),
        ]
        if no_cache:
            command.append("--no-cache")
        command.append(str(context))
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in process.stdout or []:
            db.refresh(build)
            if build.status == "cancelled":
                process.terminate()
                raise RuntimeError("Build Beam cancelado.")
            RuntimeBuildExecutionService._append(
                db, build, "[beam-build] " + line.rstrip(),
                "beam-image-building", 94,
            )
        if process.wait() != 0:
            raise RuntimeError(
                "No fue posible construir la imagen reutilizable de Beam. "
                "Modal y RunPod no fueron modificados."
            )

        RuntimeBuildExecutionService._append(
            db, build, f"[beam-build] Publicando automáticamente {image_ref}...",
            "beam-image-publishing", 97,
        )
        pushed = subprocess.Popen(
            ["docker", "push", image_ref],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in pushed.stdout or []:
            RuntimeBuildExecutionService._append(
                db, build, "[beam-build] " + line.rstrip(),
                "beam-image-publishing", 98,
            )
        if pushed.wait() != 0:
            raise RuntimeError(
                "El Build de Beam terminó, pero no se pudo publicar su imagen reutilizable. "
                "Configura una Imagen del registro real en Runtime Builder e inicia sesión "
                "con docker login en el host del backend. Deploy no construirá la imagen."
            )

        manifest["beam_runtime_image"] = {
            "fingerprint": fingerprint,
            "image_ref": image_ref,
            "published": True,
            "published_at": utc_now().isoformat(),
            "source": "manual_runtime_builder_build",
        }
        build.manifest = manifest
        build.published = True
        db.add(build)
        db.commit()
        db.refresh(build)
        RuntimeBuildExecutionService._append(
            db, build, f"[beam-build] Imagen lista para Deploy rápido: {image_ref}",
            "beam-image-ready", 99,
        )
        return image_ref

    @staticmethod
    def _require_beam_runtime_image(build, source_context):
        """Return the image created by Build; never build from Deploy."""
        fingerprint = RuntimeBuildExecutionService._beam_runtime_fingerprint(source_context)
        binding = dict((build.manifest or {}).get("beam_runtime_image") or {})
        image_ref = str(binding.get("image_ref") or "").strip()
        if not image_ref or not bool(binding.get("published")):
            raise ValueError(
                "Este build todavía no tiene una imagen Beam preparada. Ejecuta Build primero. "
                "Deploy se detuvo antes de sincronizar custom_nodes."
            )
        if str(binding.get("fingerprint") or "") != fingerprint:
            raise ValueError(
                "El runtime exportado cambió después del último Build de Beam. "
                "Ejecuta Build nuevamente y después Deploy."
            )
        return image_ref, fingerprint

    @staticmethod
    def _prepare_beam_reference_context(image_ref, fingerprint):
        """Create a genuinely tiny Beam context based on a published image."""
        import tempfile

        safe_fingerprint = str(fingerprint)[:24]
        deploy_root = (
            Path(tempfile.gettempdir())
            / "tryon-beam-reference-cache"
            / safe_fingerprint
        )
        context = deploy_root / "runtime"
        context.mkdir(parents=True, exist_ok=True)
        dockerfile = context / "Dockerfile"
        desired = f"FROM {image_ref}\n"
        if not dockerfile.exists() or dockerfile.read_text(encoding="utf-8") != desired:
            dockerfile.write_text(desired, encoding="utf-8")
        (context / ".beamignore").write_text(
            "*\n!Dockerfile\n!.beamignore\n", encoding="utf-8"
        )
        (context / ".dockerignore").write_text(
            "*\n!Dockerfile\n", encoding="utf-8"
        )
        return deploy_root, context

    @staticmethod
    def _prepare_beam_deploy_context(source_context):
        """Create or reuse a persistent Beam-only runtime context.

        Configuration-only deploys (GPU, keep-warm, workers, checkpoint, etc.)
        must reuse byte-for-byte the same Docker build context. Modal and RunPod
        never use this helper.
        """
        import tempfile

        source_context = Path(source_context).resolve()
        excluded = {"directories": 0, "files": 0}

        always_excluded_dirs = {
            ".git", ".github", ".pytest_cache", ".mypy_cache",
            ".ruff_cache", "__pycache__", "tests", "test",
            "docs", "examples", "example", "demo", "demos",
        }
        excluded_suffixes = {".pyc", ".pyo"}

        fingerprint = RuntimeBuildExecutionService._beam_runtime_fingerprint(
            source_context
        )[:24]
        cache_base = Path(tempfile.gettempdir()) / "tryon-beam-deploy-cache"
        deploy_root = cache_base / fingerprint
        deploy_context = deploy_root / "runtime"
        ready_marker = deploy_root / ".tryon-beam-context-ready.json"

        if deploy_context.is_dir() and ready_marker.is_file():
            try:
                marker = json.loads(ready_marker.read_text(encoding="utf-8"))
            except Exception:
                marker = {}
            if marker.get("fingerprint") == fingerprint:
                return deploy_root, deploy_context, marker.get("excluded", excluded), True

        staging_root = cache_base / f".{fingerprint}-{uuid.uuid4().hex}.tmp"
        staging_context = staging_root / "runtime"
        cache_base.mkdir(parents=True, exist_ok=True)

        def ignore(directory, names):
            directory_path = Path(directory)
            relative = directory_path.relative_to(source_context)
            relative_parts = tuple(part.lower() for part in relative.parts)
            ignored = []
            for name in names:
                lower = name.lower()
                candidate_parts = relative_parts + (lower,)
                candidate = directory_path / name
                exclude = False
                if candidate.is_dir():
                    if lower in always_excluded_dirs:
                        exclude = True
                    elif lower.startswith("blender-") and "windows-x64" in lower:
                        exclude = True
                    elif len(candidate_parts) >= 2 and candidate_parts[-2:] in {
                        ("assets", "videos"),
                        ("assets", "video"),
                        ("assets", "demos"),
                        ("assets", "demo"),
                        ("assets", "examples"),
                        ("assets", "example"),
                    }:
                        exclude = True
                    if exclude:
                        excluded["directories"] += 1
                else:
                    if candidate.suffix.lower() in excluded_suffixes:
                        exclude = True
                    if exclude:
                        excluded["files"] += 1
                if exclude:
                    ignored.append(name)
            return ignored

        try:
            shutil.copytree(
                source_context,
                staging_context,
                ignore=ignore,
                symlinks=True,
            )
            beamignore = staging_context / ".beamignore"
            beamignore.write_text(
                "\n".join([
                    "**/.git/**",
                    "**/.github/**",
                    "**/__pycache__/**",
                    "**/*.pyc",
                    "**/*.pyo",
                    "**/tests/**",
                    "**/test/**",
                    "**/docs/**",
                    "**/examples/**",
                    "**/example/**",
                    "**/demo/**",
                    "**/demos/**",
                    "**/assets/videos/**",
                    "**/assets/video/**",
                    "**/assets/demos/**",
                    "**/assets/demo/**",
                    "**/assets/examples/**",
                    "**/assets/example/**",
                    "**/blender-*-windows-x64/**",
                ]) + "\n",
                encoding="utf-8",
            )
            if deploy_root.exists():
                shutil.rmtree(deploy_root, ignore_errors=True)
            staging_root.replace(deploy_root)
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

        return deploy_root, deploy_context, excluded, False

    @staticmethod
    def _beam_deployment(db, build, deployment):
        """Deploy Beam from a compact provider-specific Docker context."""
        from app.services.infrastructure_provider_service import InfrastructureProviderService

        cfg = InfrastructureProviderService.get_beam(db)
        if not cfg.enabled:
            raise ValueError("Activa Beam antes del deploy.")

        from app.services.beam_credentials_service import beam_credentials_service
        beam_credentials_service.require_token(cfg)

        from app.services.beam_cli_environment_service import beam_cli_environment_service
        try:
            executable = beam_cli_environment_service.ensure(
                timeout_seconds=max(900, cfg.timeout_seconds)
            )
        except Exception as exc:
            raise ValueError(
                "No fue posible preparar el entorno aislado de Beam CLI: " + str(exc)
            ) from exc

        source_context = Path(build.context_path or "").expanduser().resolve()
        try:
            RuntimeBuildExecutionService._validate_context(source_context)
        except ValueError as exc:
            raise ValueError(
                "El contexto del runtime no es válido para desplegar en Beam: " + str(exc)
            ) from exc

        source_app = Path(__file__).resolve().parents[2] / "beam_worker" / "app.py"
        if not source_app.is_file():
            raise ValueError("No se encontró el adaptador exclusivo beam_worker/app.py.")

        RuntimeBuildExecutionService._update_deployment(
            db, build, deployment,
            phase="preparing-runtime", progress=20,
            message="Generando contexto mínimo de Beam.",
            log=f"[beam:2/6] Runtime fuente validado: {source_context}",
        )

        deploy_root = None
        home = None
        try:
            image_ref, runtime_fingerprint = (
                RuntimeBuildExecutionService._require_beam_runtime_image(
                    build, source_context
                )
            )

            fast_reference_deploy = True
            if fast_reference_deploy:
                deploy_root, context = RuntimeBuildExecutionService._prepare_beam_reference_context(
                    image_ref, runtime_fingerprint
                )
                excluded = {"directories": 0, "files": 0}
                reused_context = True
                RuntimeBuildExecutionService._update_deployment(
                    db, build, deployment,
                    phase="preparing-runtime", progress=40,
                    message="Reutilizando imagen publicada del runtime Beam.",
                    log=(
                        f"[beam] Deploy rápido desde imagen publicada: {image_ref}\n"
                        "[beam] Huella del runtime verificada; no se sincronizarán "
                        "custom_nodes ni se reconstruirá ComfyUI."
                    ),
                    beam_runtime_fingerprint=runtime_fingerprint,
                    beam_runtime_image_ref=image_ref,
                )
            else:
                # Defensive dead branch: configuration deploys must never fall back
                # to the multi-hour runtime build path.
                raise RuntimeError("Beam fast redeploy invariant violated.")
            dockerfile = context / "Dockerfile"
            # Keep the Beam handler outside the Docker build context. The handler
            # is synced as application code by the Beam CLI, while the 16+ GiB
            # runtime image remains content-identical and cacheable when only
            # Beam orchestration code changes.
            app_file = deploy_root / "tryon_beam_app.py"
            shutil.copy2(source_app, app_file)

            if not fast_reference_deploy and not reused_context:
                # Beam injects its task-queue runner into the custom image and that
                # runner imports betterproto before our handler/on_start executes.
                # Harden only Beam's temporary Docker context so Modal, RunPod and
                # the persisted runtime export remain byte-for-byte untouched.
                docker_text = dockerfile.read_text(encoding="utf-8").rstrip()

                # Beam aborts an individual image-build instruction after roughly
                # five minutes. The exported runtime installs all ComfyUI
                # requirements in one RUN, which can exceed that limit even when
                # the installation itself is healthy. Split only that Beam copy
                # into cacheable batches; the persisted runtime, Modal and RunPod
                # remain untouched.
                monolithic_comfy_install = (
                    "RUN printf '%s\\n' 'transformers>=4.50.3,<5' > "
                    "/tmp/runtime-constraints.txt && sed -Ei "
                    "'s/^transformers.*$/transformers>=4.50.3,<5/I; "
                    "/^(torch|torchvision|torchaudio|xformers|triton|"
                    "onnxruntime-gpu|flash-attn)([<>=!~ ;]|$)/Id' "
                    "/app/ComfyUI/requirements.txt && python -m pip install "
                    "--constraint /tmp/runtime-constraints.txt "
                    "-r /app/ComfyUI/requirements.txt"
                )
                split_comfy_install = "\n".join([
                    "# Beam-only: split ComfyUI dependencies into cacheable batches.",
                    "RUN printf '%s\\n' 'transformers>=4.50.3,<5' > /tmp/runtime-constraints.txt && "
                    "sed -Ei 's/^transformers.*$/transformers>=4.50.3,<5/I; "
                    "/^(torch|torchvision|torchaudio|xformers|triton|onnxruntime-gpu|flash-attn)"
                    "([<>=!~ ;]|$)/Id' /app/ComfyUI/requirements.txt",
                    "RUN /opt/conda/bin/python - <<'PY'\n"
                    "from pathlib import Path\n"
                    "src = Path('/app/ComfyUI/requirements.txt')\n"
                    "items = [line for line in src.read_text().splitlines() "
                    "if line.strip() and not line.lstrip().startswith('#')]\n"
                    "groups = [items[i::4] for i in range(4)]\n"
                    "for index, group in enumerate(groups, 1):\n"
                    "    Path(f'/tmp/comfy-requirements-{index}.txt').write_text("
                    "'\\n'.join(group) + ('\\n' if group else ''))\n"
                    "PY",
                    "RUN if [ -s /tmp/comfy-requirements-1.txt ]; then "
                    "/opt/conda/bin/python -m pip install --constraint "
                    "/tmp/runtime-constraints.txt -r /tmp/comfy-requirements-1.txt; fi",
                    "RUN if [ -s /tmp/comfy-requirements-2.txt ]; then "
                    "/opt/conda/bin/python -m pip install --constraint "
                    "/tmp/runtime-constraints.txt -r /tmp/comfy-requirements-2.txt; fi",
                    "RUN if [ -s /tmp/comfy-requirements-3.txt ]; then "
                    "/opt/conda/bin/python -m pip install --constraint "
                    "/tmp/runtime-constraints.txt -r /tmp/comfy-requirements-3.txt; fi",
                    "RUN if [ -s /tmp/comfy-requirements-4.txt ]; then "
                    "/opt/conda/bin/python -m pip install --constraint "
                    "/tmp/runtime-constraints.txt -r /tmp/comfy-requirements-4.txt; fi",
                    'RUN /opt/conda/bin/python -c "import base64; exec(base64.b64decode(\'aW1wb3J0IHJlCmltcG9ydCBzdWJwcm9jZXNzCmltcG9ydCBzeXMKcmVzdWx0ID0gc3VicHJvY2Vzcy5ydW4oW3N5cy5leGVjdXRhYmxlLCAnLW0nLCAncGlwJywgJ2NoZWNrJ10sIHRleHQ9VHJ1ZSwgc3Rkb3V0PXN1YnByb2Nlc3MuUElQRSwgc3RkZXJyPXN1YnByb2Nlc3MuU1RET1VUKQpvdXRwdXQgPSByZXN1bHQuc3Rkb3V0IG9yICcnCmlmIG91dHB1dDoKICAgIHByaW50KG91dHB1dCwgZW5kPScnIGlmIG91dHB1dC5lbmRzd2l0aCgnXG4nKSBlbHNlICdcbicpCnVuZXhwZWN0ZWQgPSBbbGluZS5zdHJpcCgpIGZvciBsaW5lIGluIG91dHB1dC5zcGxpdGxpbmVzKCkgaWYgbGluZS5zdHJpcCgpIGFuZCBsaW5lLnN0cmlwKCkgIT0gJ05vIGJyb2tlbiByZXF1aXJlbWVudHMgZm91bmQuJyBhbmQgbm90IHJlLmZ1bGxtYXRjaChyJ2RlY29yZCg/OlxzK1teIF0rKT8gaXMgbm90IHN1cHBvcnRlZCBvbiB0aGlzIHBsYXRmb3JtJywgbGluZS5zdHJpcCgpLCBmbGFncz1yZS5JR05PUkVDQVNFKV0KaWYgcmVzdWx0LnJldHVybmNvZGUgYW5kIHVuZXhwZWN0ZWQ6CiAgICBwcmludCgnW2JlYW0tYnVpbGRdIHBpcCBjaGVjayBkZXRlY3RlZCB1bnN1cHBvcnRlZCBjb25mbGljdHM6JywgZmlsZT1zeXMuc3RkZXJyKQogICAgZm9yIGxpbmUgaW4gdW5leHBlY3RlZDoKICAgICAgICBwcmludChmJyAgLSB7bGluZX0nLCBmaWxlPXN5cy5zdGRlcnIpCiAgICByYWlzZSBTeXN0ZW1FeGl0KHJlc3VsdC5yZXR1cm5jb2RlKQppZiByZXN1bHQucmV0dXJuY29kZToKICAgIHByaW50KCdbYmVhbS1idWlsZF0gSWdub3Jpbmcga25vd24gZGVjb3JkIHBsYXRmb3JtIG1ldGFkYXRhIHdhcm5pbmcgb25seS4nKQplbHNlOgogICAgcHJpbnQoJ1tiZWFtLWJ1aWxkXSBwaXAgY2hlY2sgT0snKQo=\'))"',
                ])
                if monolithic_comfy_install not in docker_text:
                    raise ValueError(
                        "No se encontró la instalación monolítica de requisitos de "
                        "ComfyUI en el Dockerfile temporal de Beam; se aborta para "
                        "no alterar una estructura desconocida."
                    )
                docker_text = docker_text.replace(
                    monolithic_comfy_install, split_comfy_install, 1
                )

                # The exported runtime also installs every custom-node requirements
                # file inside one shell loop. Beam treats that complete loop as one
                # image-build instruction, so a slow package (notably SAM 2 from
                # comfyui-impact-pack) can terminate the whole layer. Replace only
                # Beam's temporary copy with one cacheable RUN per custom node.
                # Custom nodes are materialized inside the Docker image, not in the
                # temporary Windows deploy context. Discover and install them only
                # during the Beam image build. This branch is Beam-only and leaves
                # the persisted runtime, Modal and RunPod untouched.
                custom_install_pattern = re.compile(
                    r"^RUN find /app/ComfyUI/custom_nodes -type f -name requirements\.txt "
                    r"-print \| sort \| while IFS= read -r req; do .*?; done$",
                    re.MULTILINE,
                )
                # Build one Docker RUN per custom-node requirements file from the
                # already-created Beam-only temporary context. This is intentionally
                # generated here (after copytree), so each node becomes an independent
                # cacheable layer instead of one 20+ minute shell loop.
                custom_nodes_root = context / "custom_nodes"
                requirement_files = []
                if custom_nodes_root.is_dir():
                    requirement_files = sorted(
                        path for path in custom_nodes_root.rglob("requirements.txt")
                        if path.is_file()
                    )

                general_requirements = []
                impact_requirements = None
                for requirement_path in requirement_files:
                    relative = requirement_path.relative_to(context).as_posix()
                    if relative.lower() == "custom_nodes/comfyui-impact-pack/requirements.txt":
                        impact_requirements = relative
                    else:
                        general_requirements.append(relative)

                custom_install_lines = [
                    "# Beam-only: one cacheable dependency layer per custom node.",
                ]
                for relative in general_requirements:
                    image_path = "/app/ComfyUI/" + relative
                    custom_install_lines.append(
                        "RUN req='" + image_path + "'; "
                        "echo '[runtime] Installing' \"$req\"; "
                        "sed -Ei \"/^(torch|torchvision|torchaudio|xformers|triton|"
                        "onnxruntime-gpu|flash-attn)([< >=!~ ;]|\\$)/Id\" \"$req\"; "
                        "/opt/conda/bin/python -m pip install --constraint "
                        "/tmp/runtime-constraints.txt -r \"$req\""
                    )

                if impact_requirements:
                    impact_image_path = "/app/ComfyUI/" + impact_requirements
                    custom_install_lines.extend([
                        "# Beam-only: install Impact Pack without SAM2 separately.",
                        "RUN req='" + impact_image_path + "'; "
                        "echo '[runtime] Installing Impact Pack'; "
                        "sed -Ei \"/^(torch|torchvision|torchaudio|xformers|triton|"
                        "onnxruntime-gpu|flash-attn)([< >=!~ ;]|\\$)/Id\" \"$req\"; "
                        "grep -v 'github.com/facebookresearch/sam2' \"$req\" > "
                        "/tmp/impact-pack-no-sam2.txt; "
                        "if [ -s /tmp/impact-pack-no-sam2.txt ]; then "
                        "/opt/conda/bin/python -m pip install --constraint "
                        "/tmp/runtime-constraints.txt -r /tmp/impact-pack-no-sam2.txt; fi",
                        "# Beam-only: install SAM2 without its optional CUDA extension.",
                        "RUN req='" + impact_image_path + "'; "
                        "if grep -q 'github.com/facebookresearch/sam2' \"$req\"; then "
                        "sam2_req=$(grep 'github.com/facebookresearch/sam2' \"$req\" | head -n 1); "
                        "SAM2_BUILD_CUDA=0 /opt/conda/bin/python -m pip install "
                        "--no-build-isolation --constraint /tmp/runtime-constraints.txt "
                        "\"$sam2_req\"; "
                        "/opt/conda/bin/python -c \"import sam2; "
                        "print('Beam SAM2 dependency OK')\"; fi",
                    ])

                # If the export has no custom-node requirements, remove the original
                # monolithic installer rather than failing deployment. The runtime may
                # legitimately contain nodes without Python dependencies.
                if not requirement_files:
                    custom_install_lines.append(
                        "RUN echo '[runtime] No custom-node requirements detected.'"
                    )

                split_custom_install = "\n".join(custom_install_lines)
                docker_text, custom_install_count = custom_install_pattern.subn(
                    split_custom_install, docker_text, count=1
                )
                if custom_install_count != 1:
                    raise ValueError(
                        "No se encontró la instrucción Docker esperada para instalar "
                        "requisitos de custom nodes en la copia temporal de Beam. "
                        "El runtime exportado no se modificó."
                    )

                # Beam injects its task-queue runner into the custom image and that
                # runner imports betterproto before our handler/on_start executes.
                docker_text += (
                    "\n\n# Beam-only Beta9 runner dependency and exact fail-fast validation.\n"
                    "RUN /opt/conda/bin/python -m pip uninstall -y "
                    "betterproto betterproto-beta9 || true\n"
                    "RUN /opt/conda/bin/python -m pip install --no-cache-dir "
                    "'betterproto-beta9==2.0.1' 'cloudpickle>=2.2,<4' "
                    "'watchdog>=3,<7'\n"
                    "RUN /opt/conda/bin/python -c \"import importlib; "
                    "[importlib.import_module(name) for name in ("
                    "'betterproto.grpcstub.grpcio_client','cloudpickle',"
                    "'watchdog.events')]; "
                    "print('Beam minimal runner dependencies OK')\"\n"
                    'RUN /opt/conda/bin/python -c "import base64; exec(base64.b64decode(\'aW1wb3J0IHJlCmltcG9ydCBzdWJwcm9jZXNzCmltcG9ydCBzeXMKcmVzdWx0ID0gc3VicHJvY2Vzcy5ydW4oW3N5cy5leGVjdXRhYmxlLCAnLW0nLCAncGlwJywgJ2NoZWNrJ10sIHRleHQ9VHJ1ZSwgc3Rkb3V0PXN1YnByb2Nlc3MuUElQRSwgc3RkZXJyPXN1YnByb2Nlc3MuU1RET1VUKQpvdXRwdXQgPSByZXN1bHQuc3Rkb3V0IG9yICcnCmlmIG91dHB1dDoKICAgIHByaW50KG91dHB1dCwgZW5kPScnIGlmIG91dHB1dC5lbmRzd2l0aCgnXG4nKSBlbHNlICdcbicpCnVuZXhwZWN0ZWQgPSBbbGluZS5zdHJpcCgpIGZvciBsaW5lIGluIG91dHB1dC5zcGxpdGxpbmVzKCkgaWYgbGluZS5zdHJpcCgpIGFuZCBsaW5lLnN0cmlwKCkgIT0gJ05vIGJyb2tlbiByZXF1aXJlbWVudHMgZm91bmQuJyBhbmQgbm90IHJlLmZ1bGxtYXRjaChyJ2RlY29yZCg/OlxzK1teIF0rKT8gaXMgbm90IHN1cHBvcnRlZCBvbiB0aGlzIHBsYXRmb3JtJywgbGluZS5zdHJpcCgpLCBmbGFncz1yZS5JR05PUkVDQVNFKV0KaWYgcmVzdWx0LnJldHVybmNvZGUgYW5kIHVuZXhwZWN0ZWQ6CiAgICBwcmludCgnW2JlYW0tYnVpbGRdIHBpcCBjaGVjayBkZXRlY3RlZCB1bnN1cHBvcnRlZCBjb25mbGljdHM6JywgZmlsZT1zeXMuc3RkZXJyKQogICAgZm9yIGxpbmUgaW4gdW5leHBlY3RlZDoKICAgICAgICBwcmludChmJyAgLSB7bGluZX0nLCBmaWxlPXN5cy5zdGRlcnIpCiAgICByYWlzZSBTeXN0ZW1FeGl0KHJlc3VsdC5yZXR1cm5jb2RlKQppZiByZXN1bHQucmV0dXJuY29kZToKICAgIHByaW50KCdbYmVhbS1idWlsZF0gSWdub3Jpbmcga25vd24gZGVjb3JkIHBsYXRmb3JtIG1ldGFkYXRhIHdhcm5pbmcgb25seS4nKQplbHNlOgogICAgcHJpbnQoJ1tiZWFtLWJ1aWxkXSBwaXAgY2hlY2sgT0snKQo=\'))"'
                )
                dockerfile.write_text(docker_text, encoding="utf-8")
                (deploy_root / ".tryon-beam-context-ready.json").write_text(
                    json.dumps(
                        {
                            "fingerprint": deploy_root.name,
                            "excluded": excluded,
                            "prepared_at": utc_now().isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            elif not fast_reference_deploy:
                RuntimeBuildExecutionService._update_deployment(
                    db, build, deployment,
                    phase="preparing-runtime", progress=40,
                    message="Reutilizando contexto Beam ya preparado.",
                    log=(
                        "[beam] Contexto Docker persistente reutilizado. "
                        "Las capas previas podrán usar caché."
                    ),
                )

            deployment_name = RuntimeBuildExecutionService._runtime_deployment_name(
                db, build, cfg.deployment_name or "tryon-generation-runtime"
            )
            volume_name = str(cfg.volume_name or "tryon-models").strip()
            volume_mount_path = str(getattr(cfg, "volume_mount_path", None) or "/models").strip()

            import tempfile
            home = tempfile.mkdtemp(prefix="tryon-beam-home-")
            env = os.environ.copy()
            env.update({
                "HOME": home,
                "USERPROFILE": home,
                "TRYON_BEAM_BASE_IMAGE": image_ref,
                "TRYON_BEAM_DOCKERFILE": "",
                "TRYON_BEAM_CONTEXT_DIR": str(context),
                "TRYON_BEAM_DEPLOYMENT_NAME": deployment_name,
                "TRYON_BEAM_VOLUME_NAME": volume_name,
                "TRYON_BEAM_VOLUME_PATH": volume_mount_path,
                "TRYON_BEAM_GPU": str(cfg.gpu or "L40S"),
                "TRYON_BEAM_WORKERS": str(cfg.workers),
                "TRYON_BEAM_MIN_CONTAINERS": str(cfg.min_containers),
                "TRYON_BEAM_MAX_CONTAINERS": str(cfg.max_containers),
                "TRYON_BEAM_TASKS_PER_CONTAINER": str(cfg.tasks_per_container),
                "TRYON_BEAM_KEEP_WARM_SECONDS": str(cfg.keep_warm_seconds),
                "TRYON_BEAM_MAX_PENDING_TASKS": str(cfg.max_pending_tasks),
                "TRYON_BEAM_TIMEOUT": str(cfg.timeout_seconds),
                "TRYON_BEAM_RETRIES": str(cfg.retries),
                "TRYON_BEAM_CALLBACK_URL": str(cfg.callback_url or ""),
                "TRYON_BEAM_AUTHORIZED": str(cfg.authorized).lower(),
                "TRYON_BEAM_CHECKPOINT": str(cfg.checkpoint_enabled).lower(),
            })

            auth = beam_credentials_service.configure_cli(
                executable=executable,
                config=cfg,
                env=env,
                timeout_seconds=30,
            )
            env = auth.env

            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                phase="building-image", progress=45,
                message=(
                    "Imagen publicada verificada; aplicando configuración Beam."
                    if fast_reference_deploy else
                    "Contexto Beam reutilizado; publicando configuración."
                    if reused_context else
                    "Contexto Beam listo; construyendo imagen Docker."
                ),
                log=(
                    "[beam] Contexto de referencia real: solo Dockerfile y handler."
                    if fast_reference_deploy else
                    "[beam] Contexto Docker persistente reutilizado; Beam podrá usar sus capas cacheadas."
                    if reused_context else
                    "[beam] Contexto de build creado conservando la estructura funcional del runtime. "
                    f"Se excluyeron {excluded['directories']} directorios y "
                    f"{excluded['files']} archivos prescindibles."
                ),
                app_name=deployment_name,
                volume_name=volume_name,
                beam_context_path=str(context),
            )
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                phase="deploying", progress=65,
                message="Desplegando Beam Task Queue.",
                log=(
                    "[beam:4/6] Ejecutando redeploy rápido desde imagen publicada; sin contexto de runtime."
                    if fast_reference_deploy else
                    "[beam:4/6] Ejecutando beam deploy desde el contexto de build."
                ),
            )

            from collections import deque
            import time

            output_tail = deque(maxlen=5000)
            returncode = None
            popen_kwargs = {
                "cwd": str(deploy_root),
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen(
                [
                    executable,
                    "deploy",
                    f"{app_file.name}:handler",
                    "--name",
                    deployment_name,
                ],
                **popen_kwargs,
            )
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                message="Proceso Beam iniciado.",
                log=f"[beam] Proceso local iniciado con PID {proc.pid}.",
                process_pid=proc.pid,
            )
            progress = 65
            added_files = 0
            pending_added_marker = False
            last_flush = time.monotonic()
            for raw_line in proc.stdout or []:
                line = raw_line.rstrip()
                if not line:
                    continue
                output_tail.append(line)
                if line == "Added":
                    pending_added_marker = True
                    continue
                if pending_added_marker:
                    pending_added_marker = False
                    added_files += 1
                    now = time.monotonic()
                    if added_files % 250 == 0 or now - last_flush >= 3.0:
                        progress = min(79, 65 + min(14, added_files // 250))
                        RuntimeBuildExecutionService._update_deployment(
                            db, build, deployment,
                            progress=progress,
                            message=(
                                f"Beam está sincronizando el redeploy rápido ({added_files:,} archivos)."
                                if fast_reference_deploy else
                                f"Beam está sincronizando el contexto de build ({added_files:,} archivos)."
                            ),
                            log=(
                                f"[beam] Sincronización rápida: {added_files:,} archivos."
                                if fast_reference_deploy else
                                f"[beam] Sincronización del contexto de build: {added_files:,} archivos."
                            ),
                        )
                        last_flush = now
                    continue

                progress = min(89, progress + 1)
                RuntimeBuildExecutionService._update_deployment(
                    db, build, deployment,
                    progress=progress,
                    message="Beam está construyendo y publicando el deployment.",
                    log=f"[beam] {line}",
                )
            returncode = proc.wait()
            db.expire_all()
            latest_build = db.get(RuntimeBuilderBuild, build.id)
            latest_deployment = (
                RuntimeBuildExecutionService.get_deployment(latest_build, deployment["id"])
                if latest_build else None
            )
            if latest_deployment and latest_deployment.get("status") == "cancelled":
                return

            output = "\n".join(output_tail).strip()
            if returncode != 0:
                raise ValueError("Beam deploy falló: " + (output[-4000:] or "error desconocido"))

            urls = re.findall(r"https://[^\s'\"]+", output)
            endpoint = next(
                (url.rstrip(".,?;:") for url in urls if "beam.cloud" in url),
                cfg.endpoint,
            )
            if endpoint and endpoint != cfg.endpoint:
                cfg.endpoint = endpoint
                InfrastructureProviderService.save_beam(db, cfg)

            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                phase="verifying-deployment", progress=92,
                message="Verificando despliegue Beam.",
                log=f"[beam:5/6] Beam confirmó la construcción y publicación. Endpoint: {endpoint or 'no detectado automáticamente'}",
                endpoint=endpoint,
            )
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                status="deployed", phase="completed", progress=100,
                message="Despliegue Beam completado.",
                log=(
                    "[beam:6/6] Redeploy Beam completado desde imagen publicada."
                    if fast_reference_deploy else
                    "[beam:6/6] Deployment Beam completado desde contexto de build."
                ),
                endpoint=endpoint,
                process_pid=None,
                finished_at=utc_now().isoformat(),
            )
        finally:
            if home:
                shutil.rmtree(home, ignore_errors=True)
            # deploy_root is a persistent Beam-only cache. It is deliberately
            # preserved so configuration-only redeploys reuse the exact image.

    @staticmethod
    def cancel_deployment(db, build, deployment_id):
        deployment = RuntimeBuildExecutionService.get_deployment(build, deployment_id)
        if not deployment:
            raise ValueError("Despliegue no encontrado.")
        if deployment.get("status") not in {"queued", "running"}:
            return deployment
        if deployment.get("provider") != "beam":
            raise ValueError("Esta cancelación de proceso local está disponible únicamente para Beam.")

        pid = deployment.get("process_pid")
        termination_note = "No había un proceso Beam local activo."
        if pid:
            try:
                if os.name == "nt":
                    result = subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True, text=True, timeout=20,
                    )
                    if result.returncode == 0:
                        termination_note = f"Proceso Beam PID {pid} y sus procesos hijos terminados."
                    else:
                        termination_note = f"El proceso Beam PID {pid} ya no estaba activo."
                else:
                    import signal
                    os.killpg(int(pid), signal.SIGTERM)
                    termination_note = f"Grupo de proceso Beam PID {pid} terminado."
            except (OSError, ValueError, subprocess.SubprocessError):
                termination_note = f"El proceso Beam PID {pid} ya no estaba activo."

        return RuntimeBuildExecutionService._update_deployment(
            db, build, deployment,
            status="cancelled", phase="cancelled",
            message="Despliegue Beam cancelado.",
            log=f"[beam:cancel] {termination_note}",
            error=None, process_pid=None,
            finished_at=utc_now().isoformat(),
        ) or deployment

    @staticmethod
    def run_deployment(build_id, deployment_id):
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        db = SessionLocal()
        try:
            build = db.get(RuntimeBuilderBuild, build_id)
            if not build:
                return
            deployment = RuntimeBuildExecutionService.get_deployment(build, deployment_id)
            if not deployment:
                return
            deployment["started_at"] = utc_now().isoformat()
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment, status="running", phase="validating-provider", progress=8,
                message="Validando proveedor.", log="[deploy:1/6] Validando proveedor seleccionado.",
            )
            if deployment["provider"] == "runpod":
                RuntimeBuildExecutionService._runpod_deployment(db, build, deployment)
                return
            if deployment["provider"] == "beam":
                RuntimeBuildExecutionService._beam_deployment(db, build, deployment)
                return
            if deployment["provider"] != "modal":
                raise ValueError("El proveedor seleccionado todavía no tiene adaptador de despliegue.")
            cfg = InfrastructureProviderService.get_modal(db)
            engine = ai_engine_settings_service.get(db)
            # GPU belongs to the Runtime Builder profile. Provider pricing remains global.
            runtime_cfg = db.get(RuntimeBuilderConfig, build.runtime_config_id)
            selected_gpu = str(getattr(runtime_cfg, "gpu", "") or engine.modal_gpu or "L40S").strip()
            missing = []
            if not cfg.enabled: missing.append("activar Modal")
            if not cfg.token_id: missing.append("Token ID")
            if not cfg.token_secret: missing.append("Token Secret")
            if not cfg.environment: missing.append("Environment")
            deployment_name = RuntimeBuildExecutionService._runtime_deployment_name(
                db, build, cfg.app_name
            )
            if not deployment_name: missing.append("App Name")
            if not cfg.volume_name: missing.append("Volume Name")
            if not selected_gpu: missing.append("GPU")
            if engine.modal_max_containers < engine.modal_min_containers: missing.append("rango de contenedores")
            if engine.modal_concurrency < 1: missing.append("workflows simultáneos por GPU")
            if engine.modal_input_concurrency < 1: missing.append("conexiones HTTP/WebSocket por contenedor")
            if missing:
                raise ValueError("Completa Configuración Modal y Configuración del proveedor antes del deploy: " + ", ".join(missing) + ".")
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment, phase="validating-credentials", progress=20,
                message="Validando credenciales.", log="[deploy:2/6] Credenciales y configuración de Modal validadas.",
                app_name=deployment_name, volume_name=cfg.volume_name,
            )
            executable = shutil.which("modal")
            if not executable:
                raise ValueError("Modal CLI no está instalado en el backend. Ejecuta: pip install modal")
            context = Path(build.context_path or "").expanduser().resolve()
            app_file = context / "modal_app.py"
            if not app_file.is_file():
                raise ValueError("La compilación no contiene modal_app.py. Regenera el runtime antes de desplegar.")

            # El contexto exportado es un snapshot de archivos generado en otro momento.
            # Antes de cada deploy Modal refrescamos SOLO el runtime remoto canónico
            # desde este backend para impedir que un redeploy publique runtime.py viejo.
            # No regeneramos Dockerfile/modal_app, modelos, nodos ni configuración.
            from app.services.runtime_context_generator_service import (
                RuntimeContextGeneratorService,
            )

            synced_runtime_files = RuntimeContextGeneratorService._copy_generation_runtime(context)
            synced_runtime = context / "runpod_worker" / "generation_runtime" / "runtime.py"
            if not synced_runtime.is_file():
                raise RuntimeError(
                    "No se pudo sincronizar runpod_worker/generation_runtime/runtime.py "
                    "antes del deploy Modal."
                )
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment, phase="preparing-runtime", progress=35,
                message="Preparando compilación.",
                log=(
                    f"[deploy:3/6] Contexto validado: {context}. "
                    f"Runtime remoto sincronizado ({len(synced_runtime_files)} archivos)."
                ),
            )
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment, phase="publishing-image", progress=48,
                message="Publicando imagen y aplicación en Modal.", log=f"[deploy:4/6] Ejecutando modal deploy para {deployment_name} con GPU {selected_gpu}.",
            )
            proc = subprocess.Popen(
                [executable, "deploy", "--name", deployment_name, "--env", cfg.environment, str(app_file)], cwd=str(context),
                env={
                    **InfrastructureProviderService._modal_env(cfg),
                    **RuntimeBuildExecutionService._runtime_modal_environment(db, build),
                    "TRYON_MODAL_GPU": selected_gpu,
                    "TRYON_MODAL_REGION_MODE": str(getattr(cfg, "region_mode", "automatic") or "automatic"),
                    "TRYON_MODAL_REGION": str(getattr(cfg, "region", "") or ""),
                    "TRYON_MODAL_MIN_CONTAINERS": str(engine.modal_min_containers),
                    "TRYON_MODAL_MAX_CONTAINERS": str(engine.modal_max_containers),
                    "TRYON_MODAL_CONCURRENCY": str(engine.modal_concurrency),
                    "TRYON_MODAL_INPUT_CONCURRENCY": str(engine.modal_input_concurrency),
                    "TRYON_MODAL_SCALEDOWN_WINDOW": str(engine.modal_scaledown_window_seconds),
                    "TRYON_MODAL_EXECUTION_TIMEOUT": str(engine.modal_execution_timeout_seconds),
                },
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
            progress = 48
            for line in proc.stdout or []:
                progress = min(85, progress + 2)
                RuntimeBuildExecutionService._update_deployment(
                    db, build, deployment, progress=progress,
                    message="Modal está procesando el despliegue.", log=f"[modal] {line.rstrip()}",
                )
            if proc.wait() != 0:
                raise RuntimeError("modal deploy terminó con error.")
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment, phase="verifying-deployment", progress=92,
                message="Verificando despliegue.", log="[deploy:5/6] Modal aceptó el despliegue; verificando resultado.",
            )
            deployment["finished_at"] = utc_now().isoformat()
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment, status="deployed", phase="completed", progress=100,
                message="Despliegue completado.", log="[deploy:6/6] Despliegue completado correctamente.",
            )
        except Exception as exc:
            build = db.get(RuntimeBuilderBuild, build_id)
            if build:
                deployment = RuntimeBuildExecutionService.get_deployment(build, deployment_id)
                if deployment and deployment.get("status") != "cancelled":
                    deployment["finished_at"] = utc_now().isoformat()
                    RuntimeBuildExecutionService._update_deployment(
                        db, build, deployment, status="failed", phase="failed",
                        message="El despliegue falló.", log=f"[deploy:error] {exc}", error=str(exc),
                        process_pid=None,
                    )
        finally:
            db.close()

    @staticmethod
    def publish_modal(build_id):
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        db=SessionLocal()
        try:
            build=db.get(RuntimeBuilderBuild,build_id)
            if not build or build.status not in {'succeeded','published','active'}:
                raise ValueError('El build debe finalizar correctamente antes de subirlo a Modal.')
            cfg=InfrastructureProviderService.get_modal(db)
            engine=ai_engine_settings_service.get(db)
            deployment_name=RuntimeBuildExecutionService._runtime_deployment_name(db, build, cfg.app_name)
            selected_gpu=str(getattr(db.get(RuntimeBuilderConfig, build.runtime_config_id), "gpu", "") or engine.modal_gpu or "L40S").strip()
            if not cfg.enabled or not cfg.token_id or not cfg.token_secret:
                raise ValueError('Activa y configura Modal en Proveedores de infraestructura.')
            executable=shutil.which('modal')
            if not executable:
                raise ValueError('Modal CLI no está instalado en el backend. Ejecuta: pip install modal')
            context=Path(build.context_path or '').expanduser().resolve()
            app_file=context/'modal_app.py'
            if not app_file.is_file():
                raise ValueError('La compilación seleccionada no contiene modal_app.py. Vuelve a generar el runtime con soporte Modal.')
            build.status='publishing'
            RuntimeBuildExecutionService._append(db,build,f'[modal] Publicando compilación {build.image_tag} desde {context} con GPU {selected_gpu}...','publishing',95)
            modal_env={
                **InfrastructureProviderService._modal_env(cfg),
                **RuntimeBuildExecutionService._runtime_modal_environment(db, build),
                "TRYON_MODAL_GPU": selected_gpu,
                "TRYON_MODAL_REGION_MODE": str(getattr(cfg, "region_mode", "automatic") or "automatic"),
                "TRYON_MODAL_REGION": str(getattr(cfg, "region", "") or ""),
                "TRYON_MODAL_MIN_CONTAINERS": str(engine.modal_min_containers),
                "TRYON_MODAL_MAX_CONTAINERS": str(engine.modal_max_containers),
                "TRYON_MODAL_CONCURRENCY": str(engine.modal_concurrency),
                "TRYON_MODAL_INPUT_CONCURRENCY": str(engine.modal_input_concurrency),
                "TRYON_MODAL_SCALEDOWN_WINDOW": str(engine.modal_scaledown_window_seconds),
                "TRYON_MODAL_EXECUTION_TIMEOUT": str(engine.modal_execution_timeout_seconds),
            }
            proc=subprocess.Popen(
                [executable,'deploy','--name',deployment_name,'--env',cfg.environment,str(app_file)],
                cwd=str(context),
                env=modal_env,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,
            )
            for line in proc.stdout or []:
                RuntimeBuildExecutionService._append(db,build,f'[modal] {line.rstrip()}','publishing',98)
            if proc.wait()!=0:
                raise RuntimeError('modal deploy terminó con error.')
            build.published=True
            build.status='published'
            build.phase='modal-published'
            build.progress=100
            RuntimeBuildExecutionService._append(db,build,f'[modal] Compilación publicada en la app {deployment_name}.')
        except Exception as exc:
            build=db.get(RuntimeBuilderBuild,build_id)
            if build:
                build.status='failed'; build.phase='failed'; build.error_message=str(exc)
                RuntimeBuildExecutionService._append(db,build,f'[modal:error] {exc}')
        finally:
            db.close()

    @staticmethod
    def activate(db, build):
        if not build.published: raise ValueError('Publica la imagen antes de activarla.')
        db.query(RuntimeBuilderBuild).update({RuntimeBuilderBuild.active:False})
        build.active=True; build.status='active'; build.phase='active'
        configs=db.query(RunPodConfig).filter(RunPodConfig.is_active.is_(True)).all()
        for item in configs: item.docker_image=build.image_tag
        db.add(build); db.commit(); db.refresh(build); return build

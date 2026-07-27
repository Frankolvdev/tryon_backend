import json, os, shutil, subprocess, threading, uuid
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
    def _validate_context(path):
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
        context_validation = RuntimeBuildExecutionService._validate_context(context)
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
                RuntimeBuildExecutionService._validate_context(ctx)
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            build.context_path=str(ctx)
            RuntimeBuildExecutionService._append(db,build,f"[runtime-builder] Usando exportación persistida: {ctx}","building",12)
            cmd=['docker','build','--platform',cfg.target_platform,'-t',build.image_tag,'-f',str(ctx/'Dockerfile')]
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
            inspect=subprocess.run(['docker','image','inspect',build.image_tag,'--format','{{.Id}}|{{.Size}}'],capture_output=True,text=True,timeout=30)
            if inspect.returncode==0:
                parts=inspect.stdout.strip().split('|'); build.image_id=parts[0]; build.image_size_bytes=int(parts[1]) if len(parts)>1 else None
            build.status='validating'; RuntimeBuildExecutionService._append(db,build,"[runtime-builder] Imagen construida; validando metadatos...","validating",90)
            test=subprocess.run(['docker','run','--rm','--entrypoint','python3',build.image_tag,'-c','import json; print("runtime-ok")'],capture_output=True,text=True,timeout=120)
            build.validation_result={**(build.validation_result or {}),"container_smoke_test":test.returncode==0,"smoke_output":(test.stdout+test.stderr)[-4000:]}
            if test.returncode!=0: raise RuntimeError("La prueba de arranque del contenedor falló.")
            build.status='succeeded'; build.phase='completed'; build.progress=100; build.finished_at=utc_now(); RuntimeBuildExecutionService._append(db,build,"[runtime-builder] Build y validación completados.")
            if push_after_build: RuntimeBuildExecutionService.publish(build.id)
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
    def _runpod_deployment(db, build, deployment):
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        from app.services.runpod_control_plane_service import runpod_control_plane_service

        cfg = InfrastructureProviderService.get_runpod(db)
        if not cfg.enabled or not cfg.api_key:
            raise ValueError("Activa RunPod y configura su API key en Proveedores de infraestructura.")
        if not build.image_tag:
            raise ValueError("La compilación no tiene una imagen Docker asignada.")

        RuntimeBuildExecutionService._update_deployment(
            db, build, deployment,
            phase="publishing-image", progress=25,
            message="Publicando imagen Docker.",
            log=f"[runpod:2/6] Publicando {build.image_tag} en el registro.",
            app_name=cfg.endpoint_name,
            volume_name=cfg.network_volume_name,
        )
        if not build.published:
            pushed = subprocess.run(["docker", "push", build.image_tag], capture_output=True, text=True)
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment,
                log=(pushed.stdout or "") + (pushed.stderr or ""),
            )
            if pushed.returncode != 0:
                raise RuntimeError("docker push terminó con error. Inicia sesión en el registro configurado.")
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
        endpoint_payload = {
            "templateId": template_id,
            "computeType": "GPU",
            "executionTimeoutMs": cfg.execution_timeout_seconds * 1000,
            "flashboot": cfg.flashboot,
            "gpuCount": 1,
            "gpuTypeIds": cfg.gpu_type_ids,
            "idleTimeout": cfg.idle_timeout_seconds,
            "name": cfg.endpoint_name,
            "scalerType": cfg.scaler_type,
            "scalerValue": cfg.scaler_value,
            "workersMax": cfg.workers_max,
            "workersMin": cfg.workers_min,
        }
        if cfg.allowed_cuda_versions:
            endpoint_payload["allowedCudaVersions"] = cfg.allowed_cuda_versions
        if cfg.data_center_id:
            endpoint_payload["dataCenterIds"] = [cfg.data_center_id]
        if cfg.network_volume_id:
            endpoint_payload["networkVolumeId"] = cfg.network_volume_id
            endpoint_payload["networkVolumeIds"] = [cfg.network_volume_id]

        if cfg.endpoint_id:
            endpoint = runpod_control_plane_service.update_endpoint(
                cfg.endpoint_id,
                api_key=cfg.api_key,
                payload=endpoint_payload,
                timeout_seconds=min(cfg.timeout_seconds, 120),
            )
        else:
            endpoint = runpod_control_plane_service.create_endpoint(
                api_key=cfg.api_key,
                payload=endpoint_payload,
                timeout_seconds=min(cfg.timeout_seconds, 120),
            )
            cfg.endpoint_id = str(endpoint.get("id") or "")
            InfrastructureProviderService.save_runpod(db, cfg)

        endpoint_id = str(endpoint.get("id") or cfg.endpoint_id or "")
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
    def _beam_deployment(db, build, deployment):
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        cfg=InfrastructureProviderService.get_beam(db)
        if not cfg.enabled or not cfg.api_key:
            raise ValueError("Activa Beam y configura su API key antes del deploy.")
        executable=shutil.which("beam")
        if not executable:
            raise ValueError("Beam CLI no está instalado. Ejecuta: pip install beam-client")
        RuntimeBuildExecutionService._update_deployment(db,build,deployment,phase="publishing-image",progress=25,message="Publicando imagen.",log=f"[beam:2/6] Publicando {build.image_tag}.")
        RuntimeBuildExecutionService._docker_push(build.image_tag, build, deployment, db)
        app_file=Path(__file__).resolve().parents[2]/"beam_worker"/"app.py"
        import tempfile
        home=tempfile.mkdtemp(prefix="tryon-beam-")
        env=os.environ.copy(); env.update({"HOME":home,"USERPROFILE":home,"TRYON_BEAM_IMAGE_URI":build.image_tag,"TRYON_BEAM_DEPLOYMENT_NAME":cfg.deployment_name,"TRYON_BEAM_VOLUME_NAME":cfg.volume_name,"TRYON_BEAM_VOLUME_PATH":cfg.volume_mount_path,"TRYON_BEAM_GPU":cfg.gpu,"TRYON_BEAM_CPU":str(cfg.cpu),"TRYON_BEAM_MEMORY_MB":str(cfg.memory_mb),"TRYON_BEAM_WORKERS":str(cfg.workers),"TRYON_BEAM_KEEP_WARM_SECONDS":str(cfg.keep_warm_seconds),"TRYON_BEAM_MAX_PENDING_TASKS":str(cfg.max_pending_tasks),"TRYON_BEAM_TIMEOUT":str(cfg.timeout_seconds),"TRYON_BEAM_RETRIES":str(cfg.retries),"TRYON_BEAM_CHECKPOINT":str(cfg.checkpoint_enabled).lower()})
        configured=subprocess.run([executable,"configure","default","--token",cfg.api_key],env=env,capture_output=True,text=True,timeout=30)
        if configured.returncode!=0:
            raise ValueError("Beam CLI rechazó la API key: "+(configured.stdout or configured.stderr or "")[-2000:])
        RuntimeBuildExecutionService._update_deployment(db,build,deployment,phase="deploying",progress=65,message="Desplegando Beam Task Queue.",log="[beam:4/6] Ejecutando beam deploy.")
        completed=subprocess.run([executable,"deploy",f"{app_file}:handler","--name",cfg.deployment_name],env=env,capture_output=True,text=True,timeout=max(600,cfg.timeout_seconds))
        output=(completed.stdout or completed.stderr or "").strip()
        if completed.returncode!=0: raise ValueError("Beam deploy falló: "+output[-4000:])
        import re
        urls=re.findall(r"https://[^\s'\"]+",output); endpoint=next((u.rstrip('.,') for u in urls if 'beam.cloud' in u),cfg.endpoint)
        if endpoint and endpoint!=cfg.endpoint:
            cfg.endpoint=endpoint; InfrastructureProviderService.save_beam(db,cfg)
        RuntimeBuildExecutionService._update_deployment(db,build,deployment,status="completed",phase="completed",progress=100,message="Beam desplegado.",log="[beam:6/6] Deployment Beam completado.",endpoint=endpoint,finished_at=utc_now().isoformat())

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
            # The provider form is the deployment source of truth for the GPU.
            # Fall back to Motor IA only for installations created before this field existed.
            selected_gpu = str(getattr(cfg, "gpu", "") or engine.modal_gpu or "L40S").strip()
            missing = []
            if not cfg.enabled: missing.append("activar Modal")
            if not cfg.token_id: missing.append("Token ID")
            if not cfg.token_secret: missing.append("Token Secret")
            if not cfg.environment: missing.append("Environment")
            if not cfg.app_name: missing.append("App Name")
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
                app_name=cfg.app_name, volume_name=cfg.volume_name,
            )
            executable = shutil.which("modal")
            if not executable:
                raise ValueError("Modal CLI no está instalado en el backend. Ejecuta: pip install modal")
            context = Path(build.context_path or "").expanduser().resolve()
            app_file = context / "modal_app.py"
            if not app_file.is_file():
                raise ValueError("La compilación no contiene modal_app.py. Regenera el runtime antes de desplegar.")
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment, phase="preparing-runtime", progress=35,
                message="Preparando compilación.", log=f"[deploy:3/6] Contexto validado: {context}",
            )
            RuntimeBuildExecutionService._update_deployment(
                db, build, deployment, phase="publishing-image", progress=48,
                message="Publicando imagen y aplicación en Modal.", log=f"[deploy:4/6] Ejecutando modal deploy para {cfg.app_name} con GPU {selected_gpu}.",
            )
            proc = subprocess.Popen(
                [executable, "deploy", "--name", cfg.app_name, "--env", cfg.environment, str(app_file)], cwd=str(context),
                env={**InfrastructureProviderService._modal_env(cfg),
                    "TRYON_MODAL_GPU": selected_gpu,
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
                if deployment:
                    deployment["finished_at"] = utc_now().isoformat()
                    RuntimeBuildExecutionService._update_deployment(
                        db, build, deployment, status="failed", phase="failed",
                        message="El despliegue falló.", log=f"[deploy:error] {exc}", error=str(exc),
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
            selected_gpu=str(getattr(cfg, "gpu", "") or engine.modal_gpu or "L40S").strip()
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
                "TRYON_MODAL_GPU": selected_gpu,
                "TRYON_MODAL_MIN_CONTAINERS": str(engine.modal_min_containers),
                "TRYON_MODAL_MAX_CONTAINERS": str(engine.modal_max_containers),
                "TRYON_MODAL_CONCURRENCY": str(engine.modal_concurrency),
                "TRYON_MODAL_INPUT_CONCURRENCY": str(engine.modal_input_concurrency),
                "TRYON_MODAL_SCALEDOWN_WINDOW": str(engine.modal_scaledown_window_seconds),
                "TRYON_MODAL_EXECUTION_TIMEOUT": str(engine.modal_execution_timeout_seconds),
            }
            proc=subprocess.Popen(
                [executable,'deploy','--name',cfg.app_name,'--env',cfg.environment,str(app_file)],
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
            RuntimeBuildExecutionService._append(db,build,f'[modal] Compilación publicada en la app {cfg.app_name}.')
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

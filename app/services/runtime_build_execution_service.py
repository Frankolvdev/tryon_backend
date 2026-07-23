import json, os, shutil, subprocess, threading
from pathlib import Path
from app.common.time import utc_now
from app.db.database import SessionLocal
from app.models.runtime_builder_build import RuntimeBuilderBuild
from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.models.runpod_config import RunPodConfig
from app.services.runtime_builder_service import RuntimeBuilderService

ROOT = Path(os.getenv("RUNTIME_BUILDS_DIR", "runtime_builds")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)

class RuntimeBuildExecutionService:
    @staticmethod
    def image_tag(config):
        base=config.registry_image.rstrip(":")
        return base if base.endswith(":"+config.runtime_version) else f"{base}:{config.runtime_version}"

    @staticmethod
    def diagnostic(db):
        cfg=db.query(RuntimeBuilderConfig).order_by(RuntimeBuilderConfig.id).first() or RuntimeBuilderConfig()
        try:
            result=subprocess.run(["docker","version","--format","{{.Server.Version}}"],capture_output=True,text=True,timeout=10)
            available=result.returncode==0
            version=result.stdout.strip() if available else None
        except Exception: available=False; version=None
        try:
            bx=subprocess.run(["docker","buildx","version"],capture_output=True,timeout=10).returncode==0
        except Exception: bx=False
        active=db.query(RuntimeBuilderBuild).filter(RuntimeBuilderBuild.active.is_(True)).order_by(RuntimeBuilderBuild.id.desc()).first()
        return {"docker_available":available,"docker_version":version,"buildx_available":bx,"registry_image":cfg.registry_image,"active_image":active.image_tag if active else None,"message":"Docker listo para construir." if available else "Docker no está disponible en el host del backend. También puedes ejecutar el build mediante CI usando el contexto generado."}

    @staticmethod
    def create(db, config):
        validation=RuntimeBuilderService.validate(config)
        if not validation["valid"]: raise ValueError("La configuración contiene errores y no puede compilarse.")
        build=RuntimeBuilderBuild(runtime_config_id=config.id,version=config.runtime_version,image_tag=RuntimeBuildExecutionService.image_tag(config),manifest=RuntimeBuilderService.generate(config)["runtime_manifest"],validation_result=validation)
        db.add(build); db.commit(); db.refresh(build); return build

    @staticmethod
    def start(build_id:int, push_after_build=False):
        threading.Thread(target=RuntimeBuildExecutionService._run,args=(build_id,push_after_build),daemon=True).start()

    @staticmethod
    def _append(db, build, line, phase=None, progress=None):
        build.logs=(build.logs or "") + line.rstrip() + "\n"
        if phase: build.phase=phase
        if progress is not None: build.progress=progress
        db.add(build); db.commit()

    @staticmethod
    def _run(build_id, push_after_build):
        db=SessionLocal()
        try:
            build=db.get(RuntimeBuilderBuild,build_id); cfg=db.get(RuntimeBuilderConfig,build.runtime_config_id)
            build.status="building"; build.started_at=utc_now(); RuntimeBuildExecutionService._append(db,build,"[runtime-builder] Preparando contexto reproducible...","preparing",5)
            if not cfg.export_directory:
                raise RuntimeError("Primero genera el runtime autocontenido; no existe un directorio de exportación guardado.")
            ctx = Path(cfg.export_directory).expanduser().resolve()
            if not ctx.exists() or not ctx.is_dir():
                raise RuntimeError(f"El directorio de exportación guardado no existe: {ctx}")
            if not (ctx / "Dockerfile").is_file():
                raise RuntimeError(f"La exportación no contiene Dockerfile: {ctx}")
            build.context_path=str(ctx)
            RuntimeBuildExecutionService._append(db,build,f"[runtime-builder] Usando exportación persistida: {ctx}","building",12)
            cmd=['docker','build','--platform',cfg.target_platform,'-t',build.image_tag,'-f',str(ctx/'Dockerfile'),str(ctx)]
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
    def activate(db, build):
        if not build.published: raise ValueError('Publica la imagen antes de activarla.')
        db.query(RuntimeBuilderBuild).update({RuntimeBuilderBuild.active:False})
        build.active=True; build.status='active'; build.phase='active'
        configs=db.query(RunPodConfig).filter(RunPodConfig.is_active.is_(True)).all()
        for item in configs: item.docker_image=build.image_tag
        db.add(build); db.commit(); db.refresh(build); return build

from pathlib import Path
import shutil, sys

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()

def copy_new(rel):
    src = HERE / rel
    dst = ROOT / rel
    if dst.exists():
        raise RuntimeError(f"BLINDAJE: ya existe {rel}; no se sobrescribió.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("CREADO", rel)

def patch_once(rel, old, new):
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    if new in text:
        print("YA APLICADO", rel); return
    if text.count(old) != 1:
        raise RuntimeError(f"BLINDAJE: patrón esperado no único en {rel}; no se modificó.")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("PATCH MINIMO", rel)

for rel in [
    "app/models/ancestry_media_asset.py",
    "app/schemas/ancestry_media_asset.py",
    "app/services/ancestry_media_asset_service.py",
    "app/api/v1/endpoints/admin/ancestry_media_assets.py",
    "app/api/v1/endpoints/ancestry_media_assets.py",
    "alembic/versions/06f_ancestry_media_assets.py",
]:
    copy_new(rel)

patch_once(
    "app/api/v1/endpoints/admin/router.py",
    "    body_proportion_tools,\n",
    "    body_proportion_tools,\n    ancestry_media_assets,\n",
)
patch_once(
    "app/api/v1/endpoints/admin/router.py",
    'admin_router.include_router(body_proportion_tools.router, tags=["Admin - Tools Generation"])\n',
    'admin_router.include_router(body_proportion_tools.router, tags=["Admin - Tools Generation"])\n'
    'admin_router.include_router(ancestry_media_assets.router, tags=["Admin - Tools Generation"])\n',
)
patch_once(
    "app/api/v1/router.py",
    "    ai_models,\n",
    "    ai_models,\n    ancestry_media_assets,\n",
)
patch_once(
    "app/api/v1/router.py",
    'api_router.include_router(\n    ai_models.router,\n    prefix="/ai-models",\n    tags=["AI Models"],\n)\n',
    'api_router.include_router(\n    ai_models.router,\n    prefix="/ai-models",\n    tags=["AI Models"],\n)\n'
    'api_router.include_router(\n    ancestry_media_assets.router,\n    prefix="/ancestry-assets",\n    tags=["Ancestry Assets"],\n)\n',
)
patch_once(
    "app/models/__init__.py",
    "from app.models.ai_model_profile import AiModelProfile\n",
    "from app.models.ai_model_profile import AiModelProfile\nfrom app.models.ancestry_media_asset import AncestryMediaAsset\n",
)
patch_once(
    "app/models/__init__.py",
    '__all__ = [\n',
    '__all__ = [\n    "AncestryMediaAsset",\n',
)

print("\nOK. Backend Body Proportions y sistemas existentes no fueron editados.")
print("Siguiente: python -m alembic upgrade head")

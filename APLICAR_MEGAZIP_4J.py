from __future__ import annotations

import py_compile
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNTIME_SERVICE = ROOT / "app/services/generation_module_runtime_service.py"
CONTEXT_GENERATOR = ROOT / "app/services/runtime_context_generator_service.py"


def backup(path: Path) -> Path:
    target = path.with_suffix(path.suffix + ".mega4j.bak")
    if not target.exists():
        shutil.copy2(path, target)
    return target


def patch_runtime_service(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    original = source

    import_line = (
        "from app.services.comfyui_prompt_preprocessor_service import "
        "comfyui_prompt_preprocessor_service\n"
    )
    anchor = (
        "from app.services.comfyui_local_adapter_service import "
        "comfyui_local_adapter_service\n"
    )
    if import_line not in source:
        if anchor not in source:
            raise RuntimeError(
                "No se encontró el import de comfyui_local_adapter_service."
            )
        source = source.replace(anchor, anchor + import_line, 1)

    old_return = "        return workflow, configuration, materialized"
    new_return = (
        "        workflow = comfyui_prompt_preprocessor_service.preprocess(workflow)\n"
        "        return workflow, configuration, materialized"
    )
    if new_return not in source:
        if old_return not in source:
            raise RuntimeError(
                "No se encontró el retorno de _prepare_workflow."
            )
        source = source.replace(old_return, new_return, 1)

    if source != original:
        backup(path)
        path.write_text(source, encoding="utf-8", newline="\n")


def patch_context_generator(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    original = source

    source, count = re.subn(
        "\n[ \t]*rgthree_lora_path_hotfix\s*=\s*r'''"
        ".*?"
        "\n[ \t]*'''\s*\n(?=[ \t]*startup\s*=)",
        "\n",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count == 0 and "rgthree_lora_path_hotfix" in source:
        raise RuntimeError(
            "No fue posible retirar el bloque rgthree_lora_path_hotfix."
        )

    source = re.sub(
        r'^[ \t]*"scripts/apply_runtime_hotfixes\.py":\s*'
        r"rgthree_lora_path_hotfix,\s*\n",
        "",
        source,
        count=1,
        flags=re.MULTILINE,
    )
    source = re.sub(
        r'^[ \t]*"COPY scripts/apply_runtime_hotfixes\.py '
        r'/tmp/apply_runtime_hotfixes\.py",\s*\n',
        "",
        source,
        count=1,
        flags=re.MULTILINE,
    )
    source = re.sub(
        r'^[ \t]*"RUN python /tmp/apply_runtime_hotfixes\.py '
        r'&& rm -f /tmp/apply_runtime_hotfixes\.py",\s*\n',
        "",
        source,
        count=1,
        flags=re.MULTILINE,
    )

    forbidden = (
        "rgthree_lora_path_hotfix",
        "scripts/apply_runtime_hotfixes.py",
        "/tmp/apply_runtime_hotfixes.py",
    )
    remaining = [item for item in forbidden if item in source]
    if remaining:
        raise RuntimeError(
            "Quedaron referencias al hotfix antiguo: "
            + ", ".join(remaining)
        )

    if source != original:
        backup(path)
        path.write_text(source, encoding="utf-8", newline="\n")


def main() -> None:
    for path in (RUNTIME_SERVICE, CONTEXT_GENERATOR):
        if not path.is_file():
            raise FileNotFoundError(
                f"No se encontró el archivo requerido: {path}"
            )

    patch_runtime_service(RUNTIME_SERVICE)
    patch_context_generator(CONTEXT_GENERATOR)

    for path in (
        ROOT / "app/services/comfyui_prompt_preprocessor_service.py",
        RUNTIME_SERVICE,
        CONTEXT_GENERATOR,
    ):
        py_compile.compile(str(path), doraise=True)

    print("[MEGAZIP 4J] Integración aplicada correctamente.")
    print("[MEGAZIP 4J] rgthree queda intacto.")
    print("[MEGAZIP 4J] Las rutas se normalizan antes de enviar el prompt.")


if __name__ == "__main__":
    main()

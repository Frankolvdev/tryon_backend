from __future__ import annotations

import ast
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read_valid_git_file(relative_path: str) -> str:
    for revision in ("HEAD", "origin/main"):
        result = subprocess.run(
            ["git", "show", f"{revision}:{relative_path}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            continue
        try:
            ast.parse(result.stdout)
        except SyntaxError:
            continue
        return result.stdout
    raise RuntimeError(
        f"No se encontró una versión Git válida para {relative_path}. "
        "Ejecuta git fetch origin y vuelve a aplicar el MegaZIP."
    )


def restore_external_ai_job_service() -> None:
    relative = "app/services/external_ai_job_service.py"
    target = ROOT / relative
    try:
        ast.parse(target.read_text(encoding="utf-8"))
        print(f"[OK] {relative} ya tiene sintaxis válida.")
        return
    except SyntaxError:
        pass
    target.write_text(
        read_valid_git_file(relative),
        encoding="utf-8",
        newline="\n",
    )
    print(f"[REPARADO] {relative} restaurado desde Git.")


def patch_comfyui_adapter() -> None:
    relative = "app/services/comfyui_local_adapter_service.py"
    target = ROOT / relative
    source = target.read_text(encoding="utf-8")

    import_line = (
        "from app.services.comfyui_prompt_preprocessor_service import "
        "comfyui_prompt_preprocessor_service\n"
    )
    if import_line not in source:
        anchor = "from app.core.config import settings\n"
        if anchor not in source:
            raise RuntimeError(
                f"No se encontró el punto de importación esperado en {relative}."
            )
        source = source.replace(anchor, anchor + import_line, 1)

    old_body = (
        "        resolved_client_id = client_id or uuid4().hex\n"
        "        body: dict[str, Any] = {\n"
        "            \"prompt\": workflow,\n"
        "            \"client_id\": resolved_client_id,\n"
        "        }\n"
    )

    new_body = (
        "        resolved_client_id = client_id or uuid4().hex\n"
        "\n"
        "        normalized_workflow = "
        "comfyui_prompt_preprocessor_service.preprocess(workflow)\n"
        "        comfyui_prompt_preprocessor_service."
        "assert_no_windows_model_paths(normalized_workflow)\n"
        "\n"
        "        body: dict[str, Any] = {\n"
        "            \"prompt\": normalized_workflow,\n"
        "            \"client_id\": resolved_client_id,\n"
        "        }\n"
    )

    if new_body not in source:
        if old_body not in source:
            raise RuntimeError(
                f"No se encontró queue_prompt con la estructura esperada en {relative}."
            )
        source = source.replace(old_body, new_body, 1)

    ast.parse(source)
    target.write_text(source, encoding="utf-8", newline="\n")
    print("[OK] Barrera final instalada antes de POST /prompt.")


def main() -> None:
    restore_external_ai_job_service()
    patch_comfyui_adapter()

    for relative in (
        "app/services/external_ai_job_service.py",
        "app/services/comfyui_prompt_preprocessor_service.py",
        "app/services/comfyui_local_adapter_service.py",
    ):
        ast.parse((ROOT / relative).read_text(encoding="utf-8"))

    print("[OK] Validación de sintaxis completada.")


if __name__ == "__main__":
    main()

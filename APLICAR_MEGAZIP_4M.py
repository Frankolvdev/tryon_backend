from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "app/services/comfyui_local_adapter_service.py"


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")

    import_line = (
        "from app.services.comfyui_prompt_preprocessor_service import "
        "comfyui_prompt_preprocessor_service\n"
    )
    import_anchor = "from app.core.config import settings\n"

    if import_line not in source:
        if import_anchor not in source:
            raise RuntimeError(
                "No se encontró el import esperado en "
                "app/services/comfyui_local_adapter_service.py"
            )
        source = source.replace(import_anchor, import_anchor + import_line, 1)

    old_block = (
        "        resolved_client_id = client_id or uuid4().hex\n"
        "        body: dict[str, Any] = {\n"
        "            \"prompt\": workflow,\n"
        "            \"client_id\": resolved_client_id,\n"
        "        }\n"
    )
    new_block = (
        "        resolved_client_id = client_id or uuid4().hex\n"
        "        normalized_workflow = (\n"
        "            comfyui_prompt_preprocessor_service.preprocess(workflow)\n"
        "        )\n"
        "        comfyui_prompt_preprocessor_service.assert_no_windows_model_paths(\n"
        "            normalized_workflow\n"
        "        )\n"
        "        body: dict[str, Any] = {\n"
        "            \"prompt\": normalized_workflow,\n"
        "            \"client_id\": resolved_client_id,\n"
        "        }\n"
    )

    if new_block not in source:
        if old_block not in source:
            raise RuntimeError(
                "No se encontró el bloque exacto de queue_prompt. "
                "No se modificó ningún archivo."
            )
        source = source.replace(old_block, new_block, 1)

    ast.parse(source)
    TARGET.write_text(source, encoding="utf-8", newline="\n")
    print("[OK] comfyui_local_adapter_service.py actualizado.")
    print("[OK] Normalización final instalada antes de POST /prompt.")


if __name__ == "__main__":
    main()

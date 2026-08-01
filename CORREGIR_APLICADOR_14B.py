from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
INSTALLER = ROOT / "APLICAR_MEGAZIP_14B.py"


OLD_BLOCK = '''    modal_import_anchor = "from pathlib import Path\\nimport modal\\n"
    modal_import_insert = (
        "from pathlib import Path\\n"
        "import modal\\n"
        "from comfyui_runtime_engine.modal import ModalSnapshotAdapter\\n"
    )
    text = replace_once(
        text, modal_import_anchor, modal_import_insert, "import del adaptador Modal"
    )
'''


NEW_BLOCK = '''    modal_import_marker = (
        "from comfyui_runtime_engine.modal import ModalSnapshotAdapter"
    )
    if modal_import_marker not in text:
        modal_method_index = text.find("def _modal_app(")
        if modal_method_index < 0:
            raise RuntimeError(
                "No se encontró RuntimeBuilderService._modal_app."
            )

        modal_prefix = text[:modal_method_index]
        modal_section = text[modal_method_index:]

        import_anchor = "import modal"
        import_index = modal_section.find(import_anchor)
        if import_index >= 0:
            line_end = modal_section.find("\\n", import_index)
            if line_end < 0:
                line_end = import_index + len(import_anchor)
            modal_section = (
                modal_section[:line_end]
                + "\\n"
                + modal_import_marker
                + modal_section[line_end:]
            )
        else:
            constant_candidates = (
                "APP_NAME =",
                "COMFYUI_PORT =",
                "STARTUP_TIMEOUT =",
                "EXECUTION_TIMEOUT =",
            )
            positions = [
                modal_section.find(candidate)
                for candidate in constant_candidates
                if modal_section.find(candidate) >= 0
            ]
            if not positions:
                raise RuntimeError(
                    "No fue posible localizar los imports o constantes "
                    "del modal_app generado."
                )
            insert_at = min(positions)
            modal_section = (
                modal_section[:insert_at]
                + modal_import_marker
                + "\\n"
                + modal_section[insert_at:]
            )

        text = modal_prefix + modal_section
'''


def main() -> int:
    if not INSTALLER.is_file():
        raise RuntimeError(
            f"No se encontró el instalador original: {INSTALLER}"
        )

    text = INSTALLER.read_text(encoding="utf-8")

    if NEW_BLOCK in text:
        print("El hotfix 14B ya estaba aplicado.")
        return 0

    if OLD_BLOCK not in text:
        raise RuntimeError(
            "El instalador 14B no contiene el bloque esperado. "
            "No se modificó ningún archivo del backend."
        )

    backup = INSTALLER.with_suffix(".py.before_import_hotfix.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")

    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    INSTALLER.write_text(text, encoding="utf-8", newline="\n")

    print("Hotfix aplicado a APLICAR_MEGAZIP_14B.py.")
    print("Ahora ejecuta nuevamente:")
    print("python .\\APLICAR_MEGAZIP_14B.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

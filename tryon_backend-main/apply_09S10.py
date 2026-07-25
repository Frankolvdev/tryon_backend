from __future__ import annotations

from pathlib import Path
import shutil
import sys


TARGET = Path("app/services/subscription_service.py")
IMPORT_LINE = "from app.common.time import utc_now\n"


def main() -> int:
    if not TARGET.exists():
        print(
            f"ERROR: No se encontró {TARGET}. "
            "Ejecuta este script desde la raíz de tryon_backend.",
            file=sys.stderr,
        )
        return 1

    source = TARGET.read_text(encoding="utf-8")

    if IMPORT_LINE in source:
        print("OK: utc_now ya está importado; no se realizaron cambios.")
        return 0

    lines = source.splitlines(keepends=True)
    insert_at = None

    for index, line in enumerate(lines):
        if line.startswith("from app.") or line.startswith("import app."):
            insert_at = index
            break

    if insert_at is None:
        for index, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = index
                break

    if insert_at is None:
        print(
            "ERROR: No se encontró un bloque de imports válido.",
            file=sys.stderr,
        )
        return 1

    backup = TARGET.with_suffix(".py.09S10.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)

    lines.insert(insert_at, IMPORT_LINE)
    TARGET.write_text("".join(lines), encoding="utf-8")

    print("OK: utc_now importado en app/services/subscription_service.py")
    print(f"Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

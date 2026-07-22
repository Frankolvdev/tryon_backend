from __future__ import annotations

import compileall
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "requirements.txt",
        root / "alembic.ini",
        root / "app" / "main.py",
        root / "app" / "core" / "config.py",
        root / "app" / "api" / "v1",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    if missing:
        print("Faltan archivos esenciales:", file=sys.stderr)
        for path in missing:
            print(f"- {path}", file=sys.stderr)
        return 1

    print("[1/2] Estructura Backend: OK")
    print("[2/2] Compilación sintáctica")
    app_ok = compileall.compile_dir(root / "app", quiet=1)
    alembic_ok = compileall.compile_dir(root / "alembic", quiet=1)
    if not (app_ok and alembic_ok):
        print("La compilación sintáctica encontró errores.", file=sys.stderr)
        return 1
    print("Backend listo para validación de integración.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

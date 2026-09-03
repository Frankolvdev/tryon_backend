"""Aplica el hotfix de registro para no enviar turnstile_token al modelo User.

Ejecutar una sola vez desde la raíz de tryon_backend:

    python scripts/apply_registration_turnstile_hotfix.py
"""

from __future__ import annotations

from pathlib import Path
import shutil


TARGET = Path("app/services/user_service.py")

OLD = """        age_confirmed = bool(
            user_dict.pop(
                "age_confirmed",
                False,
            )
        )

        user_dict["email"] = (
"""

NEW = """        age_confirmed = bool(
            user_dict.pop(
                "age_confirmed",
                False,
            )
        )

        # turnstile_token pertenece al contrato de registro y se utiliza
        # únicamente para la validación anti-bot. No es una columna de User.
        user_dict.pop(
            "turnstile_token",
            None,
        )

        user_dict["email"] = (
"""


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(
            f"No se encontró {TARGET}. Ejecuta este script desde la raíz del backend."
        )

    content = TARGET.read_text(encoding="utf-8")

    if NEW in content:
        print("El hotfix ya estaba aplicado. No se realizaron cambios.")
        return

    if OLD not in content:
        raise SystemExit(
            "No se encontró el bloque esperado en user_service.py. "
            "No se modificó ningún archivo para evitar sobrescribir código distinto."
        )

    backup = TARGET.with_suffix(".py.before_turnstile_hotfix")
    shutil.copy2(TARGET, backup)

    updated = content.replace(OLD, NEW, 1)
    TARGET.write_text(updated, encoding="utf-8", newline="\n")

    print(f"Hotfix aplicado correctamente en: {TARGET}")
    print(f"Respaldo creado en: {backup}")
    print("Puedes eliminar el respaldo después de verificar el registro.")


if __name__ == "__main__":
    main()

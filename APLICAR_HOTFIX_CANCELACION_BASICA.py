from __future__ import annotations

import py_compile
import shutil
from pathlib import Path

TARGET = Path('app/services/generation_module_runtime_service.py')

OLD_CANCEL = '''            item.cancel_requested = True
            item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="warning", message="Cancellation requested."))
            was_queued = item.status == "queued"
            if was_queued:
                item.status = "cancelled"
                item.finished_at = utc_now()
                item.provider_status = "cancelled_before_dispatch"
                item.logs.append(GenerationModuleExecutionLog(timestamp=item.finished_at, level="warning", message="Queued execution cancelled before dispatch."))
            snapshot = item.model_copy(deep=True)
'''

NEW_CANCEL = '''            item.cancel_requested = True
            cancelled_at = utc_now()
            was_queued = item.status == "queued"
            item.status = "cancelled"
            item.finished_at = cancelled_at
            item.heartbeat_at = cancelled_at
            item.provider_status = (
                "cancelled_before_dispatch" if was_queued else "cancelled_locally"
            )
            running_step = next((step for step in item.steps if step.status == "running"), None)
            if running_step is not None:
                running_step.status = "cancelled"
                running_step.finished_at = cancelled_at
                running_step.error = "Execution cancelled by user."
            item.logs.append(
                GenerationModuleExecutionLog(
                    timestamp=cancelled_at,
                    level="warning",
                    message=(
                        "Queued execution cancelled before dispatch."
                        if was_queued
                        else "Execution cancelled locally. Remote interruption requested when supported."
                    ),
                )
            )
            snapshot = item.model_copy(deep=True)
'''

OLD_EXCEPT = '''        except Exception as exc:
            with self._lock:
                item = self._items[execution_id]
                item.status = "failed"; item.error = str(exc)
                running = next((s for s in item.steps if s.status == "running"), None)
                if running:
                    running.status = "failed"; running.error = str(exc); running.finished_at = utc_now()
                item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="error", step_key=running.step_key if running else None, message=str(exc)))
'''

NEW_EXCEPT = '''        except Exception as exc:
            with self._lock:
                item = self._items[execution_id]
                running = next((s for s in item.steps if s.status == "running"), None)
                if item.cancel_requested or item.status == "cancelled":
                    item.status = "cancelled"
                    item.error = None
                    if running:
                        running.status = "cancelled"
                        running.error = "Execution cancelled by user."
                        running.finished_at = utc_now()
                    item.logs.append(
                        GenerationModuleExecutionLog(
                            timestamp=utc_now(),
                            level="warning",
                            step_key=running.step_key if running else None,
                            message="Provider execution stopped after cancellation request.",
                        )
                    )
                else:
                    item.status = "failed"; item.error = str(exc)
                    if running:
                        running.status = "failed"; running.error = str(exc); running.finished_at = utc_now()
                    item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="error", step_key=running.step_key if running else None, message=str(exc)))
'''


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f'No se encontró {TARGET}. Ejecuta este script desde la raíz del Backend.')

    original = TARGET.read_text(encoding='utf-8')
    updated = original

    if NEW_CANCEL not in updated:
        if OLD_CANCEL not in updated:
            raise SystemExit('No se encontró el bloque actual de cancelación. El repositorio cambió y no se modificó nada.')
        updated = updated.replace(OLD_CANCEL, NEW_CANCEL, 1)

    if NEW_EXCEPT not in updated:
        if OLD_EXCEPT not in updated:
            raise SystemExit('No se encontró el bloque actual de manejo de errores. El repositorio cambió y no se modificó nada.')
        updated = updated.replace(OLD_EXCEPT, NEW_EXCEPT, 1)

    if updated == original:
        print('El hotfix ya estaba aplicado; no hubo cambios.')
        return

    backup = TARGET.with_suffix(TARGET.suffix + '.bak_cancel_basic')
    shutil.copy2(TARGET, backup)
    TARGET.write_text(updated, encoding='utf-8', newline='\n')

    try:
        py_compile.compile(str(TARGET), doraise=True)
    except Exception:
        shutil.copy2(backup, TARGET)
        raise

    print(f'Hotfix aplicado correctamente en {TARGET}')
    print(f'Respaldo creado en {backup}')


if __name__ == '__main__':
    main()

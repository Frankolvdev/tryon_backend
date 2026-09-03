from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.beam_file_manager_service import BeamFileManagerError, BeamFileManagerService

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class BeamUploadV4Item:
    local_path: Path
    relative_path: str
    remote_path: str
    size: int


class BeamUploadEngineV4Service:
    """Beam Upload Engine V4: una transferencia multipart por árbol.

    Este motor está deliberadamente aislado del File Manager y del resto de
    proveedores. Usa la sintaxis documentada por Beam CLI 0.2.207:

        beam cp <directorio-local> beam://<volumen>/<ruta>

    La CLI decide si usa multipart (comportamiento predeterminado cuando el
    Gateway dispone del servicio externo de archivos). El backend únicamente
    prepara un árbol filtrado, abre un solo proceso y retransmite su salida en
    vivo; no ejecuta un ``beam cp`` por archivo ni usa ``rm``/``mv``.
    """

    ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    BYTE_RE = re.compile(
        r"(?P<done>[0-9]+(?:[.,][0-9]+)?)\s*(?P<done_unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)"
        r"\s*(?:/|of)\s*"
        r"(?P<total>[0-9]+(?:[.,][0-9]+)?)\s*(?P<total_unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)",
        re.IGNORECASE,
    )
    SPEED_RE = re.compile(
        r"(?P<speed>[0-9]+(?:[.,][0-9]+)?)\s*(?P<unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)\s*/\s*s",
        re.IGNORECASE,
    )
    PERCENT_RE = re.compile(r"(?P<percent>[0-9]{1,3}(?:[.,][0-9]+)?)\s*%")
    ETA_RE = re.compile(r"(?:ETA|remaining)\s*[:=]?\s*(?P<eta>[^|·]+)", re.IGNORECASE)
    UNIT = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
    }

    @classmethod
    def _number(cls, value: str, unit: str) -> int:
        return int(float(value.replace(",", ".")) * cls.UNIT[unit.upper()])

    @classmethod
    def _parse_native_progress(cls, text: str, total_bytes: int) -> dict[str, Any]:
        clean = cls.ANSI_RE.sub("", text or "").strip()
        result: dict[str, Any] = {"native_line": clean}
        byte_match = cls.BYTE_RE.search(clean)
        if byte_match:
            result["bytes_transferred"] = cls._number(
                byte_match.group("done"), byte_match.group("done_unit")
            )
            result["native_bytes_total"] = cls._number(
                byte_match.group("total"), byte_match.group("total_unit")
            )
        else:
            percent_match = cls.PERCENT_RE.search(clean)
            if percent_match and total_bytes > 0:
                percent = min(100.0, max(0.0, float(percent_match.group("percent").replace(",", "."))))
                result["bytes_transferred"] = int(total_bytes * percent / 100.0)

        speed_match = cls.SPEED_RE.search(clean)
        if speed_match:
            result["speed_bps"] = cls._number(speed_match.group("speed"), speed_match.group("unit"))
        eta_match = cls.ETA_RE.search(clean)
        if eta_match:
            result["eta"] = eta_match.group("eta").strip()
        return result

    @staticmethod
    def _reader(stream: Any, output_queue: queue.Queue[tuple[str, str]], source: str) -> None:
        try:
            buffer = ""
            while True:
                chunk = stream.read(1)
                if chunk == "":
                    if buffer.strip():
                        output_queue.put((source, buffer))
                    break
                if chunk in {"\r", "\n"}:
                    if buffer.strip():
                        output_queue.put((source, buffer))
                    buffer = ""
                else:
                    buffer += chunk
        finally:
            try:
                stream.close()
            except Exception:
                pass

    @classmethod
    def _make_filtered_tree(
        cls,
        *,
        models_root: Path,
        pending: list[BeamUploadV4Item],
    ) -> tuple[Path, Path]:
        """Crea un staging ligero sin alterar el árbol original.

        Intenta hardlinks (instantáneos y sin duplicar decenas de GB). Como
        salvaguarda para filesystems que no los soporten, copia únicamente el
        archivo afectado.
        """
        temporary_root = Path(tempfile.mkdtemp(prefix="tryon-beam-v4-", dir=str(models_root.parent)))
        upload_root = temporary_root / "models"
        upload_root.mkdir(parents=True, exist_ok=True)
        for item in pending:
            target = upload_root.joinpath(*item.relative_path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(item.local_path, target)
            except OSError:
                shutil.copy2(item.local_path, target)
        return temporary_root, upload_root

    @classmethod
    def _detect_file_from_line(
        cls,
        clean_line: str,
        items: list[BeamUploadV4Item],
    ) -> BeamUploadV4Item | None:
        normalized = clean_line.replace("\\", "/").casefold()
        # Se comprueba primero la ruta relativa completa para evitar colisiones
        # entre archivos con el mismo nombre en categorías diferentes.
        for item in items:
            if item.relative_path.casefold() in normalized:
                return item
        for item in items:
            if item.local_path.name.casefold() in normalized:
                return item
        return None

    @classmethod
    def upload_tree(
        cls,
        db: Session,
        *,
        volume: str,
        models_root: Path,
        remote_prefix: str,
        overwrite: bool,
        timeout: int,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        emit = on_progress or (lambda _event: None)
        cfg, executable, env, home = BeamFileManagerService._env(db)
        selected = BeamFileManagerService._volume_name(cfg, volume)
        prefix = BeamFileManagerService._clean(remote_prefix)
        root = Path(models_root).resolve()
        paths = sorted(path for path in root.rglob("*") if path.is_file())
        items = [
            BeamUploadV4Item(
                local_path=path,
                relative_path=path.relative_to(root).as_posix(),
                remote_path="/".join(
                    part for part in (prefix, path.relative_to(root).as_posix()) if part
                ),
                size=path.stat().st_size,
            )
            for path in paths
        ]
        total_files = len(items)
        total_bytes = sum(item.size for item in items)
        temporary_root: Path | None = None

        try:
            try:
                cli_version = BeamFileManagerService._run_in_context(
                    executable=executable, env=env, args=["--version"], timeout=30
                ).strip()
            except Exception as exc:
                cli_version = f"no disponible ({exc})"

            emit({
                "phase": "inventory",
                "total": total_files,
                "bytes_total": total_bytes,
                "volume_name": selected,
                "path": prefix,
                "cli_version": cli_version,
            })

            pending: list[BeamUploadV4Item] = []
            skipped: list[BeamUploadV4Item] = []
            if overwrite:
                pending = list(items)
            else:
                # Una única fase de inventario: cada carpeta remota se consulta
                # una vez y sus nombres se reutilizan para todos sus archivos.
                parents = sorted({
                    item.remote_path.rsplit("/", 1)[0] if "/" in item.remote_path else ""
                    for item in items
                })
                inventories = {
                    parent: BeamFileManagerService._list_parent_names_in_context(
                        executable=executable,
                        env=env,
                        volume=selected,
                        parent=parent,
                    )
                    for parent in parents
                }
                for item in items:
                    parent, name = (
                        item.remote_path.rsplit("/", 1)
                        if "/" in item.remote_path
                        else ("", item.remote_path)
                    )
                    if name in inventories.get(parent, set()):
                        skipped.append(item)
                    else:
                        pending.append(item)

            bytes_skipped = sum(item.size for item in skipped)
            for index, item in enumerate(skipped, start=1):
                emit({
                    "phase": "file-skipped",
                    "total": total_files,
                    "files_skipped": index,
                    "bytes_skipped": sum(entry.size for entry in skipped[:index]),
                    "bytes_total": total_bytes,
                    "file_name": item.local_path.name,
                    "file_size": item.size,
                    "remote": item.remote_path,
                })

            if not pending:
                emit({
                    "phase": "completed",
                    "total": total_files,
                    "files_uploaded": 0,
                    "files_skipped": len(skipped),
                    "bytes_uploaded": 0,
                    "bytes_skipped": bytes_skipped,
                    "bytes_total": total_bytes,
                })
                return {
                    "files_total": total_files,
                    "files_uploaded": 0,
                    "files_skipped": len(skipped),
                    "bytes_total": total_bytes,
                    "bytes_uploaded": 0,
                    "bytes_skipped": bytes_skipped,
                    "workers": 0,
                    "transfer_modes": [],
                    "volume_name": selected,
                    "path": prefix,
                    "cli_version": cli_version,
                }

            pending_bytes = sum(item.size for item in pending)
            for index, item in enumerate(pending, start=1):
                emit({
                    "phase": "file-queued",
                    "queue_index": index,
                    "queued_total": len(pending),
                    "total": total_files,
                    "bytes_total": total_bytes,
                    "file_name": item.local_path.name,
                    "file_size": item.size,
                    "remote": item.remote_path,
                })

            temporary_root, upload_root = cls._make_filtered_tree(
                models_root=root,
                pending=pending,
            )
            destination = BeamFileManagerService._uri(selected, prefix)
            command = [executable, "cp", str(upload_root), destination]
            emit({
                "phase": "transfer-start",
                "total": total_files,
                "files_pending": len(pending),
                "files_skipped": len(skipped),
                "bytes_pending": pending_bytes,
                "bytes_skipped": bytes_skipped,
                "bytes_total": total_bytes,
                "destination": destination,
                "multipart": "auto",
            })

            process = subprocess.Popen(
                command,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                bufsize=0,
            )
            output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
            threads = [
                threading.Thread(target=cls._reader, args=(process.stdout, output_queue, "stdout"), daemon=True),
                threading.Thread(target=cls._reader, args=(process.stderr, output_queue, "stderr"), daemon=True),
            ]
            for thread in threads:
                thread.start()

            started = time.monotonic()
            lines: list[str] = []
            latest_bytes = 0
            latest_speed = 0
            current_item: BeamUploadV4Item | None = None
            last_emit = 0.0
            while process.poll() is None or any(thread.is_alive() for thread in threads) or not output_queue.empty():
                if time.monotonic() - started > max(60, int(timeout)):
                    process.kill()
                    raise BeamFileManagerError(
                        f"Beam CLI excedió {max(60, int(timeout))} segundos subiendo el árbol de modelos."
                    )
                try:
                    source, line = output_queue.get(timeout=0.15)
                except queue.Empty:
                    continue
                clean = cls.ANSI_RE.sub("", line).strip()
                if not clean:
                    continue
                lines.append(f"[{source}] {clean}")
                detected = cls._detect_file_from_line(clean, pending)
                if detected is not None:
                    current_item = detected
                parsed = cls._parse_native_progress(clean, pending_bytes)
                native_bytes = int(parsed.get("bytes_transferred") or 0)
                if native_bytes:
                    latest_bytes = max(latest_bytes, min(pending_bytes, native_bytes))
                if int(parsed.get("speed_bps") or 0) > 0:
                    latest_speed = int(parsed["speed_bps"])
                now = time.monotonic()
                if now - last_emit >= 0.25 or latest_bytes >= pending_bytes:
                    event = {
                        "phase": "transfer-progress",
                        "total": total_files,
                        "files_pending": len(pending),
                        "files_skipped": len(skipped),
                        "bytes_transferred": latest_bytes,
                        "bytes_pending": pending_bytes,
                        "bytes_skipped": bytes_skipped,
                        "bytes_total": total_bytes,
                        "speed_bps": latest_speed,
                        "native_line": clean,
                        "eta": parsed.get("eta"),
                    }
                    if current_item is not None:
                        event.update({
                            "file_name": current_item.local_path.name,
                            "file_size": current_item.size,
                            "remote": current_item.remote_path,
                        })
                    emit(event)
                    last_emit = now

            return_code = process.wait()
            output = "\n".join(lines)
            if return_code != 0:
                raise BeamFileManagerError((output or "Beam CLI terminó con error")[-10000:])

            # La única operación de transferencia terminó correctamente: todos
            # los archivos pendientes pertenecen a la misma confirmación V4.
            completed_bytes = 0
            for index, item in enumerate(pending, start=1):
                completed_bytes += item.size
                emit({
                    "phase": "file-completed",
                    "completed_index": index,
                    "files_uploaded": index,
                    "files_skipped": len(skipped),
                    "total": total_files,
                    "bytes_uploaded": completed_bytes,
                    "bytes_skipped": bytes_skipped,
                    "bytes_total": total_bytes,
                    "file_name": item.local_path.name,
                    "file_size": item.size,
                    "remote": item.remote_path,
                })

            emit({
                "phase": "completed",
                "total": total_files,
                "files_uploaded": len(pending),
                "files_skipped": len(skipped),
                "bytes_uploaded": pending_bytes,
                "bytes_skipped": bytes_skipped,
                "bytes_total": total_bytes,
            })
            return {
                "files_total": total_files,
                "files_uploaded": len(pending),
                "files_skipped": len(skipped),
                "bytes_total": total_bytes,
                "bytes_uploaded": pending_bytes,
                "bytes_skipped": bytes_skipped,
                "workers": 1,
                "transfer_modes": ["directory-multipart-auto"],
                "volume_name": selected,
                "path": prefix,
                "cli_version": cli_version,
            }
        finally:
            if temporary_root is not None:
                shutil.rmtree(temporary_root, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)

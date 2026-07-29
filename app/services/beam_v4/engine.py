from __future__ import annotations

import json
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

from app.models.system_setting import SystemSetting
from app.services.beam_cli_environment_service import beam_cli_environment_service
from app.services.beam_credentials_service import beam_credentials_service

ProgressCallback = Callable[[dict[str, Any]], None]


class BeamV4Error(RuntimeError):
    """Error exclusivo del motor de transferencia Beam V4."""


@dataclass(frozen=True)
class _Item:
    source: Path
    relative: str
    remote: str
    size: int


class BeamV4Engine:
    """Sube un árbol completo con el modo multipart de Beam CLI 0.2.207.

    Este módulo no importa servicios de Modal, RunPod, Docker ni el File Manager
    de Beam. La transferencia se ejecuta con ``beam cp --multipart . DESTINO``
    usando ``cwd`` en el staging filtrado. Así evitamos pasar rutas Windows como
    SOURCE y evitamos el fallback V1 que genera destinos con barras invertidas.
    """

    CONFIG_KEY = "infrastructure_provider_beam"
    ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    SIZE_RE = re.compile(
        r"(?P<done>\d+(?:[.,]\d+)?)\s*(?P<du>B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)"
        r"\s*(?:/|of)\s*"
        r"(?P<total>\d+(?:[.,]\d+)?)\s*(?P<tu>B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)",
        re.IGNORECASE,
    )
    SPEED_RE = re.compile(
        r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)\s*/\s*s",
        re.IGNORECASE,
    )
    PERCENT_RE = re.compile(r"(?P<value>\d{1,3}(?:[.,]\d+)?)\s*%")
    ETA_RE = re.compile(r"(?:ETA|remaining)\s*[:=]?\s*(?P<value>[^|·]+)", re.IGNORECASE)
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

    @staticmethod
    def _clean_remote(path: str | None) -> str:
        return "/".join(
            part for part in str(path or "").replace("\\", "/").split("/")
            if part not in {"", ".", ".."}
        )

    @classmethod
    def _destination(cls, volume: str, prefix: str) -> str:
        clean_volume = cls._clean_remote(volume)
        if not clean_volume or "/" in clean_volume:
            raise BeamV4Error("El nombre del volumen Beam no es válido.")
        clean_prefix = cls._clean_remote(prefix)
        return f"beam://{clean_volume}" + (f"/{clean_prefix}" if clean_prefix else "")

    @classmethod
    def _load_config(cls, db: Session) -> dict[str, Any]:
        row = db.query(SystemSetting).filter(SystemSetting.key == cls.CONFIG_KEY).first()
        if not row or not row.value_json:
            raise BeamV4Error("Configura el proveedor Beam antes de exportar modelos.")
        try:
            data = json.loads(row.value_json)
        except Exception as exc:
            raise BeamV4Error("La configuración guardada de Beam no es JSON válido.") from exc
        if not isinstance(data, dict):
            raise BeamV4Error("La configuración guardada de Beam no es válida.")
        return data

    @classmethod
    def _prepare_cli(cls, db: Session) -> tuple[dict[str, Any], str, dict[str, str], Path]:
        config = cls._load_config(db)
        token = beam_credentials_service.normalize_token(str(config.get("api_key") or ""))
        if not token:
            raise BeamV4Error("Configura el Token de Beam.")
        executable = beam_cli_environment_service.ensure(timeout_seconds=30)
        home = Path(tempfile.mkdtemp(prefix="tryon-beam-v4-home-"))
        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "USERPROFILE": str(home),
            "COLUMNS": "500",
            "TERM": "dumb",
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            "BEAM_TOKEN": token,
        })
        workspace = str(config.get("workspace") or "").strip()
        if workspace:
            env["BEAM_WORKSPACE_ID"] = workspace
        try:
            auth = beam_credentials_service.configure_cli(
                executable=executable,
                config=type("BeamConfig", (), {
                    "api_key": token,
                    "workspace": workspace,
                })(),
                env=env,
                timeout_seconds=45,
            )
        except Exception:
            shutil.rmtree(home, ignore_errors=True)
            raise
        return config, executable, auth.env, home

    @classmethod
    def _run(cls, executable: str, env: dict[str, str], args: list[str], timeout: int) -> str:
        try:
            completed = subprocess.run(
                [executable, *args],
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=max(10, int(timeout)),
            )
        except subprocess.TimeoutExpired as exc:
            raise BeamV4Error(f"Beam CLI excedió {timeout} segundos ejecutando {' '.join(args)}") from exc
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip()
        )
        if completed.returncode != 0:
            raise BeamV4Error((output or "Beam CLI terminó con error")[-8000:])
        return output

    @classmethod
    def _remote_names(
        cls,
        executable: str,
        env: dict[str, str],
        volume: str,
        parent: str,
    ) -> set[str]:
        target = volume + (f"/{parent}" if parent else "")
        try:
            output = cls._run(executable, env, ["ls", target], 300)
        except BeamV4Error as exc:
            lowered = str(exc).casefold()
            if any(marker in lowered for marker in ("not found", "does not exist", "unable to stat")):
                return set()
            raise
        names: set[str] = set()
        clean = cls.ANSI_RE.sub("", output)
        for raw in clean.splitlines():
            line = raw.strip()
            if not line or line.startswith(("Name ", "─", "━", "═")):
                continue
            columns = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
            if columns:
                name = columns[0].rstrip("/")
                if name and name not in {".", "..", ".keep"}:
                    names.add(name)
        return names

    @classmethod
    def _filtered_tree(cls, root: Path, pending: list[_Item]) -> tuple[Path, Path]:
        temp_root = Path(tempfile.mkdtemp(prefix="tryon-beam-v4-tree-", dir=str(root.parent)))
        upload_root = temp_root / "upload"
        upload_root.mkdir(parents=True, exist_ok=True)
        for item in pending:
            target = upload_root.joinpath(*item.relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(item.source, target)
            except OSError:
                shutil.copy2(item.source, target)
        return temp_root, upload_root

    @staticmethod
    def _reader(stream: Any, output: queue.Queue[tuple[str, str]], name: str) -> None:
        try:
            buffer = ""
            while True:
                char = stream.read(1)
                if char == "":
                    if buffer.strip():
                        output.put((name, buffer))
                    return
                if char in {"\r", "\n"}:
                    if buffer.strip():
                        output.put((name, buffer))
                    buffer = ""
                else:
                    buffer += char
        finally:
            try:
                stream.close()
            except Exception:
                pass

    @classmethod
    def _bytes(cls, value: str, unit: str) -> int:
        return int(float(value.replace(",", ".")) * cls.UNIT[unit.upper()])

    @classmethod
    def _parse_progress(cls, line: str, total: int) -> dict[str, Any]:
        result: dict[str, Any] = {"native_line": line}
        size = cls.SIZE_RE.search(line)
        if size:
            result["bytes_transferred"] = cls._bytes(size.group("done"), size.group("du"))
        else:
            percent = cls.PERCENT_RE.search(line)
            if percent and total > 0:
                value = min(100.0, max(0.0, float(percent.group("value").replace(",", "."))))
                result["bytes_transferred"] = int(total * value / 100)
        speed = cls.SPEED_RE.search(line)
        if speed:
            result["speed_bps"] = cls._bytes(speed.group("value"), speed.group("unit"))
        eta = cls.ETA_RE.search(line)
        if eta:
            result["eta"] = eta.group("value").strip()
        return result

    @classmethod
    def upload(
        cls,
        db: Session,
        *,
        models_root: Path,
        remote_prefix: str,
        overwrite: bool,
        timeout: int,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        emit = on_progress or (lambda _event: None)
        config, executable, env, home = cls._prepare_cli(db)
        temp_tree: Path | None = None
        try:
            volume = cls._clean_remote(str(config.get("volume_name") or ""))
            if not volume or "/" in volume:
                raise BeamV4Error("Configura un nombre de volumen Beam válido.")
            prefix = cls._clean_remote(remote_prefix)
            destination = cls._destination(volume, prefix)
            root = Path(models_root).resolve()
            items = [
                _Item(
                    source=path,
                    relative=path.relative_to(root).as_posix(),
                    remote="/".join(part for part in (prefix, path.relative_to(root).as_posix()) if part),
                    size=path.stat().st_size,
                )
                for path in sorted(root.rglob("*")) if path.is_file()
            ]
            total_bytes = sum(item.size for item in items)
            try:
                cli_version = cls._run(executable, env, ["--version"], 30)
            except Exception as exc:
                cli_version = f"no disponible ({exc})"
            emit({"phase": "inventory", "total": len(items), "bytes_total": total_bytes,
                  "volume_name": volume, "path": prefix, "cli_version": cli_version})

            pending: list[_Item] = []
            skipped: list[_Item] = []
            if overwrite:
                pending = list(items)
            else:
                parents = sorted({item.remote.rsplit("/", 1)[0] if "/" in item.remote else "" for item in items})
                inventory = {parent: cls._remote_names(executable, env, volume, parent) for parent in parents}
                for item in items:
                    parent, name = item.remote.rsplit("/", 1) if "/" in item.remote else ("", item.remote)
                    (skipped if name in inventory.get(parent, set()) else pending).append(item)

            skipped_bytes = 0
            for index, item in enumerate(skipped, 1):
                skipped_bytes += item.size
                emit({"phase": "file-skipped", "total": len(items), "files_skipped": index,
                      "bytes_skipped": skipped_bytes, "file_name": item.source.name,
                      "file_size": item.size, "remote": item.remote})
            if not pending:
                result = {"files_total": len(items), "files_uploaded": 0, "files_skipped": len(skipped),
                          "bytes_total": total_bytes, "bytes_uploaded": 0, "bytes_skipped": skipped_bytes,
                          "workers": 0, "transfer_modes": [], "volume_name": volume,
                          "path": prefix, "cli_version": cli_version}
                emit({"phase": "completed", **result})
                return result

            pending_bytes = sum(item.size for item in pending)
            for index, item in enumerate(pending, 1):
                emit({"phase": "file-queued", "queue_index": index, "queued_total": len(pending),
                      "total": len(items), "file_name": item.source.name,
                      "file_size": item.size, "remote": item.remote})

            temp_tree, upload_root = cls._filtered_tree(root, pending)
            # --multipart es intencional: evita el fallback V1 de Beam 0.2.207,
            # que en Windows convierte volume/ruta en volume\\ruta y falla.
            command = [executable, "cp", "--multipart", ".", destination]
            emit({"phase": "transfer-start", "total": len(items), "files_pending": len(pending),
                  "files_skipped": len(skipped), "bytes_pending": pending_bytes,
                  "bytes_skipped": skipped_bytes, "bytes_total": total_bytes,
                  "destination": destination, "multipart": True,
                  "command": f"beam cp --multipart . {destination}"})

            process = subprocess.Popen(
                command,
                cwd=str(upload_root),
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
            while process.poll() is None or any(thread.is_alive() for thread in threads) or not output_queue.empty():
                if time.monotonic() - started > max(60, int(timeout)):
                    process.kill()
                    raise BeamV4Error(f"Beam multipart excedió {timeout} segundos.")
                try:
                    source, raw = output_queue.get(timeout=0.15)
                except queue.Empty:
                    continue
                line = cls.ANSI_RE.sub("", raw).strip()
                if not line:
                    continue
                lines.append(f"[{source}] {line}")
                parsed = cls._parse_progress(line, pending_bytes)
                latest_bytes = max(latest_bytes, min(pending_bytes, int(parsed.get("bytes_transferred") or 0)))
                latest_speed = int(parsed.get("speed_bps") or latest_speed)
                emit({"phase": "transfer-progress", "total": len(items),
                      "files_pending": len(pending), "files_skipped": len(skipped),
                      "bytes_transferred": latest_bytes, "bytes_pending": pending_bytes,
                      "bytes_skipped": skipped_bytes, "bytes_total": total_bytes,
                      "speed_bps": latest_speed, "eta": parsed.get("eta"),
                      "native_line": line})

            return_code = process.wait()
            output = "\n".join(lines)
            if return_code != 0:
                lowered = output.casefold()
                if "unable to find volume" in lowered and "\\" in output:
                    raise BeamV4Error(
                        "Beam CLI volvió a usar el transporte V1 de Windows pese a --multipart. "
                        "El Gateway de este volumen probablemente no tiene habilitado el file service multipart. "
                        "Detalle: " + output[-7000:]
                    )
                raise BeamV4Error((output or "Beam multipart terminó con error")[-9000:])

            uploaded_bytes = 0
            for index, item in enumerate(pending, 1):
                uploaded_bytes += item.size
                emit({"phase": "file-completed", "completed_index": index,
                      "files_uploaded": index, "files_skipped": len(skipped),
                      "total": len(items), "bytes_uploaded": uploaded_bytes,
                      "bytes_skipped": skipped_bytes, "bytes_total": total_bytes,
                      "file_name": item.source.name, "file_size": item.size,
                      "remote": item.remote})
            result = {"files_total": len(items), "files_uploaded": len(pending),
                      "files_skipped": len(skipped), "bytes_total": total_bytes,
                      "bytes_uploaded": pending_bytes, "bytes_skipped": skipped_bytes,
                      "workers": 1, "transfer_modes": ["directory-multipart-forced"],
                      "volume_name": volume, "path": prefix, "cli_version": cli_version}
            emit({"phase": "completed", **result})
            return result
        finally:
            if temp_tree is not None:
                shutil.rmtree(temp_tree, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)

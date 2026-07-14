import base64
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.runpod_runtime_config_service import (
    runpod_runtime_config_service,
)


logger = logging.getLogger(__name__)


class RunPodServerlessAdapterService:
    TERMINAL_STATUSES = {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
    }

    SUCCESS_STATUSES = {
        "COMPLETED",
    }

    FAILURE_STATUSES = {
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
    }

    def _headers(
        self,
        db: Session,
    ) -> dict[str, str]:
        api_key = (
            runpod_runtime_config_service
            .api_key(db)
        )

        if not api_key:
            raise RuntimeError(
                "RunPod API key is not configured."
            )

        return {
            "Authorization": (
                f"Bearer {api_key}"
            ),
            "Content-Type": "application/json",
        }

    def _endpoint_id(
        self,
        db: Session,
        override: str | None = None,
    ) -> str:
        endpoint_id = (
            override
            or runpod_runtime_config_service
            .endpoint_id(db)
        )

        if not endpoint_id:
            raise RuntimeError(
                "RunPod endpoint ID is not configured."
            )

        return endpoint_id

    def _endpoint_url(
        self,
        db: Session,
        *,
        endpoint_id: str,
        operation: str,
    ) -> str:
        base_url = (
            runpod_runtime_config_service
            .base_url(db)
        )

        return (
            f"{base_url}/"
            f"{endpoint_id}/"
            f"{operation.lstrip('/')}"
        )

    def _output_root(self) -> Path:
        local_storage_dir = Path(
            str(
                getattr(
                    settings,
                    "LOCAL_STORAGE_DIR",
                    "storage",
                )
            )
        )

        output_dir = (
            local_storage_dir
            / "runpod-results"
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        return output_dir

    def health(
        self,
        db: Session,
        *,
        endpoint_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_endpoint_id = (
            self._endpoint_id(
                db,
                override=endpoint_id,
            )
        )

        try:
            with httpx.Client(
                timeout=(
                    runpod_runtime_config_service
                    .http_timeout_seconds()
                ),
            ) as client:
                response = client.get(
                    self._endpoint_url(
                        db,
                        endpoint_id=(
                            resolved_endpoint_id
                        ),
                        operation="health",
                    ),
                    headers=self._headers(db),
                )

                response.raise_for_status()

                return {
                    "available": True,
                    "endpoint_id": (
                        resolved_endpoint_id
                    ),
                    "data": response.json(),
                }

        except Exception as error:
            return {
                "available": False,
                "endpoint_id": (
                    resolved_endpoint_id
                ),
                "error": str(error),
            }

    def submit_job(
        self,
        db: Session,
        *,
        input_data: dict[str, Any],
        endpoint_id: str | None = None,
        webhook_url: str | None = None,
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_endpoint_id = (
            self._endpoint_id(
                db,
                override=endpoint_id,
            )
        )

        body: dict[str, Any] = {
            "input": input_data,
        }

        resolved_webhook_url = (
            webhook_url
            or runpod_runtime_config_service
            .callback_url(db)
        )

        if resolved_webhook_url:
            body["webhook"] = resolved_webhook_url

        if policy:
            body["policy"] = policy

        with httpx.Client(
            timeout=(
                runpod_runtime_config_service
                .http_timeout_seconds()
            ),
        ) as client:
            response = client.post(
                self._endpoint_url(
                    db,
                    endpoint_id=(
                        resolved_endpoint_id
                    ),
                    operation="run",
                ),
                headers=self._headers(db),
                json=body,
            )

            response.raise_for_status()

            data = response.json()

        provider_job_id = data.get("id")

        if not provider_job_id:
            raise RuntimeError(
                "RunPod did not return a job ID."
            )

        return {
            "provider": "runpod_serverless",
            "provider_job_id": str(
                provider_job_id
            ),
            "endpoint_id": (
                resolved_endpoint_id
            ),
            "status": data.get(
                "status",
                "IN_QUEUE",
            ),
            "response": data,
        }

    def get_status(
        self,
        db: Session,
        *,
        provider_job_id: str,
        endpoint_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_endpoint_id = (
            self._endpoint_id(
                db,
                override=endpoint_id,
            )
        )

        with httpx.Client(
            timeout=(
                runpod_runtime_config_service
                .http_timeout_seconds()
            ),
        ) as client:
            response = client.get(
                self._endpoint_url(
                    db,
                    endpoint_id=(
                        resolved_endpoint_id
                    ),
                    operation=(
                        "status/"
                        f"{provider_job_id}"
                    ),
                ),
                headers=self._headers(db),
            )

            response.raise_for_status()

            data = response.json()

        return {
            "provider_job_id": (
                provider_job_id
            ),
            "endpoint_id": (
                resolved_endpoint_id
            ),
            "status": str(
                data.get(
                    "status",
                    "UNKNOWN",
                )
            ).upper(),
            "output": data.get("output"),
            "error": data.get("error"),
            "execution_time": data.get(
                "executionTime"
            ),
            "delay_time": data.get(
                "delayTime"
            ),
            "raw": data,
        }

    def cancel_job(
        self,
        db: Session,
        *,
        provider_job_id: str,
        endpoint_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_endpoint_id = (
            self._endpoint_id(
                db,
                override=endpoint_id,
            )
        )

        with httpx.Client(
            timeout=(
                runpod_runtime_config_service
                .http_timeout_seconds()
            ),
        ) as client:
            response = client.post(
                self._endpoint_url(
                    db,
                    endpoint_id=(
                        resolved_endpoint_id
                    ),
                    operation=(
                        "cancel/"
                        f"{provider_job_id}"
                    ),
                ),
                headers=self._headers(db),
                json={},
            )

            response.raise_for_status()

            try:
                data = response.json()
            except ValueError:
                data = {
                    "message": response.text,
                }

        return {
            "canceled": True,
            "provider_job_id": (
                provider_job_id
            ),
            "endpoint_id": (
                resolved_endpoint_id
            ),
            "response": data,
        }

    def purge_queue(
        self,
        db: Session,
        *,
        endpoint_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_endpoint_id = (
            self._endpoint_id(
                db,
                override=endpoint_id,
            )
        )

        with httpx.Client(
            timeout=(
                runpod_runtime_config_service
                .http_timeout_seconds()
            ),
        ) as client:
            response = client.post(
                self._endpoint_url(
                    db,
                    endpoint_id=(
                        resolved_endpoint_id
                    ),
                    operation="purge-queue",
                ),
                headers=self._headers(db),
                json={},
            )

            response.raise_for_status()

            return response.json()

    def _progress_from_status(
        self,
        status: str,
        data: dict[str, Any],
    ) -> float:
        progress = data.get("progress")

        if isinstance(progress, (int, float)):
            return min(
                max(float(progress), 0.0),
                99.0,
            )

        output = data.get("output")

        if isinstance(output, dict):
            output_progress = output.get(
                "progress"
            )

            if isinstance(
                output_progress,
                (int, float),
            ):
                return min(
                    max(
                        float(output_progress),
                        0.0,
                    ),
                    99.0,
                )

        if status == "IN_QUEUE":
            return 2.0

        if status == "IN_PROGRESS":
            return 50.0

        if status == "COMPLETED":
            return 100.0

        return 0.0

    def wait_for_completion(
        self,
        db: Session,
        *,
        provider_job_id: str,
        endpoint_id: str,
        timeout_seconds: int,
        progress_callback=None,
        cancellation_callback=None,
    ) -> dict[str, Any]:
        started_at = time.monotonic()
        polling_interval = (
            runpod_runtime_config_service
            .polling_interval_seconds()
        )

        while True:
            elapsed = (
                time.monotonic()
                - started_at
            )

            if elapsed >= timeout_seconds:
                try:
                    self.cancel_job(
                        db,
                        provider_job_id=(
                            provider_job_id
                        ),
                        endpoint_id=endpoint_id,
                    )
                except Exception:
                    logger.exception(
                        "Could not cancel timed-out "
                        "RunPod job %s.",
                        provider_job_id,
                    )

                raise TimeoutError(
                    "RunPod job exceeded the "
                    f"configured timeout of "
                    f"{timeout_seconds} seconds."
                )

            if (
                cancellation_callback
                and cancellation_callback()
            ):
                self.cancel_job(
                    db,
                    provider_job_id=(
                        provider_job_id
                    ),
                    endpoint_id=endpoint_id,
                )

                raise InterruptedError(
                    "RunPod job cancellation "
                    "was requested."
                )

            status_data = self.get_status(
                db,
                provider_job_id=(
                    provider_job_id
                ),
                endpoint_id=endpoint_id,
            )

            status = status_data["status"]

            progress = (
                self._progress_from_status(
                    status,
                    status_data["raw"],
                )
            )

            if progress_callback:
                progress_callback(
                    progress,
                    (
                        "RunPod job is waiting "
                        "for a worker."
                        if status == "IN_QUEUE"
                        else (
                            "RunPod worker is "
                            "processing the job."
                            if status
                            == "IN_PROGRESS"
                            else (
                                "RunPod job status: "
                                f"{status}."
                            )
                        )
                    ),
                    {
                        "provider_job_id": (
                            provider_job_id
                        ),
                        "endpoint_id": endpoint_id,
                        "provider_status": status,
                        "elapsed_seconds": elapsed,
                        "delay_time": (
                            status_data.get(
                                "delay_time"
                            )
                        ),
                        "execution_time": (
                            status_data.get(
                                "execution_time"
                            )
                        ),
                    },
                )

            if status in self.TERMINAL_STATUSES:
                return status_data

            time.sleep(
                max(
                    polling_interval,
                    0.5,
                )
            )

    def _safe_filename(
        self,
        url: str,
        default_suffix: str = ".bin",
    ) -> str:
        parsed = urlparse(url)

        filename = Path(
            parsed.path
        ).name

        if filename:
            return filename

        return (
            uuid4().hex
            + default_suffix
        )

    def _download_url(
        self,
        *,
        url: str,
        job_public_id: str,
    ) -> dict[str, Any]:
        with httpx.Client(
            timeout=300,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()

            content = response.content
            content_type = (
                response.headers.get(
                    "content-type"
                )
            )

        job_directory = (
            self._output_root()
            / job_public_id
        )

        job_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = (
            uuid4().hex[:8]
            + "-"
            + self._safe_filename(url)
        )

        destination = (
            job_directory
            / filename
        )

        destination.write_bytes(content)

        return self._file_result(
            destination=destination,
            content_type=content_type,
            size_bytes=len(content),
            source_url=url,
        )

    def _decode_base64(
        self,
        *,
        value: str,
        job_public_id: str,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        encoded_value = value

        if value.startswith("data:"):
            header, _, encoded_value = (
                value.partition(",")
            )

            if not content_type:
                content_type = (
                    header
                    .replace("data:", "")
                    .split(";")[0]
                )

        content = base64.b64decode(
            encoded_value
        )

        suffix = ".bin"

        suffix_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
        }

        if content_type in suffix_map:
            suffix = suffix_map[content_type]

        resolved_filename = (
            filename
            or (
                uuid4().hex
                + suffix
            )
        )

        job_directory = (
            self._output_root()
            / job_public_id
        )

        job_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination = (
            job_directory
            / Path(
                resolved_filename
            ).name
        )

        destination.write_bytes(content)

        return self._file_result(
            destination=destination,
            content_type=content_type,
            size_bytes=len(content),
            source_url=None,
        )

    def _file_result(
        self,
        *,
        destination: Path,
        content_type: str | None,
        size_bytes: int,
        source_url: str | None,
    ) -> dict[str, Any]:
        storage_root = Path(
            str(
                getattr(
                    settings,
                    "LOCAL_STORAGE_DIR",
                    "storage",
                )
            )
        )

        try:
            storage_key = (
                destination
                .relative_to(storage_root)
                .as_posix()
            )
        except ValueError:
            storage_key = (
                destination.as_posix()
            )

        return {
            "filename": destination.name,
            "local_path": str(destination),
            "storage_key": storage_key,
            "public_url": (
                "/local-files/"
                + storage_key
            ),
            "size_bytes": size_bytes,
            "content_type": content_type,
            "source_url": source_url,
        }

    def collect_outputs(
        self,
        *,
        output: Any,
        job_public_id: str,
        download_outputs: bool = True,
    ) -> list[dict[str, Any]]:
        collected: list[
            dict[str, Any]
        ] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                url_value = (
                    value.get("url")
                    or value.get("image_url")
                    or value.get("video_url")
                    or value.get("download_url")
                )

                if (
                    download_outputs
                    and isinstance(
                        url_value,
                        str,
                    )
                    and url_value.startswith(
                        ("http://", "https://")
                    )
                ):
                    collected.append(
                        self._download_url(
                            url=url_value,
                            job_public_id=(
                                job_public_id
                            ),
                        )
                    )

                base64_value = (
                    value.get("base64")
                    or value.get("image_base64")
                    or value.get("data")
                )

                if (
                    download_outputs
                    and isinstance(
                        base64_value,
                        str,
                    )
                    and (
                        value.get("encoding")
                        == "base64"
                        or base64_value.startswith(
                            "data:"
                        )
                    )
                ):
                    collected.append(
                        self._decode_base64(
                            value=base64_value,
                            job_public_id=(
                                job_public_id
                            ),
                            filename=value.get(
                                "filename"
                            ),
                            content_type=value.get(
                                "content_type"
                            ),
                        )
                    )

                for nested_value in (
                    value.values()
                ):
                    walk(nested_value)

            elif isinstance(value, list):
                for item in value:
                    walk(item)

            elif (
                download_outputs
                and isinstance(value, str)
                and value.startswith(
                    ("http://", "https://")
                )
            ):
                collected.append(
                    self._download_url(
                        url=value,
                        job_public_id=(
                            job_public_id
                        ),
                    )
                )

        walk(output)

        unique: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in collected:
            identity = str(
                item.get("local_path")
                or item.get("source_url")
            )

            if identity in seen:
                continue

            seen.add(identity)
            unique.append(item)

        return unique

    def execute_submitted_job(
        self,
        db: Session,
        *,
        provider_job_id: str,
        endpoint_id: str,
        job_public_id: str,
        timeout_seconds: int,
        download_outputs: bool = True,
        progress_callback=None,
        cancellation_callback=None,
    ) -> dict[str, Any]:
        status_data = self.wait_for_completion(
            db,
            provider_job_id=provider_job_id,
            endpoint_id=endpoint_id,
            timeout_seconds=timeout_seconds,
            progress_callback=progress_callback,
            cancellation_callback=(
                cancellation_callback
            ),
        )

        status = status_data["status"]

        if status == "CANCELLED":
            raise InterruptedError(
                "RunPod job was canceled."
            )

        if status == "TIMED_OUT":
            raise TimeoutError(
                "RunPod marked the job as timed out."
            )

        if status == "FAILED":
            raise RuntimeError(
                "RunPod job failed: "
                + json.dumps(
                    status_data.get("error"),
                    ensure_ascii=False,
                    default=str,
                )
            )

        if status not in self.SUCCESS_STATUSES:
            raise RuntimeError(
                "RunPod returned unsupported "
                f"terminal status '{status}'."
            )

        output = status_data.get("output")

        files = self.collect_outputs(
            output=output,
            job_public_id=job_public_id,
            download_outputs=download_outputs,
        )

        return {
            "success": True,
            "provider": "runpod_serverless",
            "provider_job_id": (
                provider_job_id
            ),
            "endpoint_id": endpoint_id,
            "provider_status": status,
            "output": output,
            "files": files,
            "file_count": len(files),
            "execution_time": (
                status_data.get(
                    "execution_time"
                )
            ),
            "delay_time": (
                status_data.get(
                    "delay_time"
                )
            ),
            "raw": status_data["raw"],
        }


runpod_serverless_adapter_service = (
    RunPodServerlessAdapterService()
)
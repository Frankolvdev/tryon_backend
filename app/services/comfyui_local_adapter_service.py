import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from uuid import uuid4

import httpx
import websocket

from app.core.config import settings


logger = logging.getLogger(__name__)


class ComfyUILocalAdapterService:
    def _base_url(self) -> str:
        configured_url = getattr(
            settings,
            "COMFYUI_BASE_URL",
            None,
        )

        if configured_url:
            return str(configured_url).rstrip("/")

        return "http://127.0.0.1:8188"

    def _timeout_seconds(self) -> float:
        return float(
            getattr(
                settings,
                "COMFYUI_HTTP_TIMEOUT_SECONDS",
                30,
            )
        )

    def _output_root(self) -> Path:
        local_storage_dir = str(
            getattr(
                settings,
                "LOCAL_STORAGE_DIR",
                "storage",
            )
        )

        output_dir = (
            Path(local_storage_dir)
            / "comfyui-results"
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        return output_dir

    def _websocket_url(
        self,
        *,
        client_id: str,
    ) -> str:
        parsed = urlparse(self._base_url())

        scheme = (
            "wss"
            if parsed.scheme == "https"
            else "ws"
        )

        return (
            f"{scheme}://{parsed.netloc}"
            f"/ws?clientId={client_id}"
        )

    def health(self) -> dict[str, Any]:
        try:
            with httpx.Client(
                timeout=self._timeout_seconds(),
            ) as client:
                response = client.get(
                    f"{self._base_url()}/system_stats"
                )

                response.raise_for_status()

                return {
                    "available": True,
                    "base_url": self._base_url(),
                    "system_stats": response.json(),
                }

        except Exception as error:
            return {
                "available": False,
                "base_url": self._base_url(),
                "error": str(error),
            }

    def upload_input(
        self,
        *,
        content: bytes,
        filename: str,
        content_type: str,
        subfolder: str = "",
    ) -> dict[str, Any]:
        files = {"image": (filename, content, content_type)}
        data = {"type": "input", "overwrite": "false"}
        if subfolder:
            data["subfolder"] = subfolder
        with httpx.Client(timeout=self._timeout_seconds()) as client:
            response = client.post(
                f"{self._base_url()}/upload/image",
                files=files,
                data=data,
            )
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, dict) or not result.get("name"):
            raise RuntimeError("ComfyUI did not accept the generation input file.")
        return result

    def queue_prompt(
        self,
        *,
        workflow: dict[str, Any],
        client_id: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_client_id = (
            client_id
            or uuid4().hex
        )

        body: dict[str, Any] = {
            "prompt": workflow,
            "client_id": resolved_client_id,
        }

        if extra_data:
            body["extra_data"] = extra_data

        with httpx.Client(
            timeout=self._timeout_seconds(),
        ) as client:
            response = client.post(
                f"{self._base_url()}/prompt",
                json=body,
            )

            response.raise_for_status()

            data = response.json()

        prompt_id = data.get("prompt_id")

        if not prompt_id:
            raise RuntimeError(
                "ComfyUI did not return a prompt_id."
            )

        node_errors = data.get(
            "node_errors",
            {},
        )

        if node_errors:
            raise RuntimeError(
                "ComfyUI rejected the workflow: "
                + json.dumps(
                    node_errors,
                    ensure_ascii=False,
                    default=str,
                )
            )

        return {
            "prompt_id": str(prompt_id),
            "client_id": resolved_client_id,
            "number": data.get("number"),
            "node_errors": node_errors,
        }

    def get_history(
        self,
        *,
        prompt_id: str,
    ) -> dict[str, Any] | None:
        with httpx.Client(
            timeout=self._timeout_seconds(),
        ) as client:
            response = client.get(
                f"{self._base_url()}/history/"
                f"{prompt_id}"
            )

            response.raise_for_status()

            history = response.json()

        item = history.get(prompt_id)

        if isinstance(item, dict):
            return item

        return None

    def get_queue(self) -> dict[str, Any]:
        with httpx.Client(
            timeout=self._timeout_seconds(),
        ) as client:
            response = client.get(
                f"{self._base_url()}/queue"
            )

            response.raise_for_status()

            return response.json()

    def interrupt(self) -> bool:
        try:
            with httpx.Client(
                timeout=self._timeout_seconds(),
            ) as client:
                response = client.post(
                    f"{self._base_url()}/interrupt",
                    json={},
                )

                response.raise_for_status()

            return True

        except Exception as error:
            logger.warning(
                "Could not interrupt ComfyUI: %s",
                error,
            )

            return False

    def delete_queued_prompt(
        self,
        *,
        prompt_id: str,
    ) -> bool:
        try:
            with httpx.Client(
                timeout=self._timeout_seconds(),
            ) as client:
                response = client.post(
                    f"{self._base_url()}/queue",
                    json={
                        "delete": [prompt_id],
                    },
                )

                response.raise_for_status()

            return True

        except Exception as error:
            logger.warning(
                "Could not delete queued ComfyUI prompt %s: %s",
                prompt_id,
                error,
            )

            return False

    def cancel_prompt(
        self,
        *,
        prompt_id: str,
    ) -> dict[str, Any]:
        deleted = self.delete_queued_prompt(
            prompt_id=prompt_id,
        )

        interrupted = self.interrupt()

        return {
            "prompt_id": prompt_id,
            "deleted_from_queue": deleted,
            "interrupt_sent": interrupted,
        }

    def _is_history_complete(
        self,
        history_item: dict[str, Any],
    ) -> bool:
        status = history_item.get(
            "status",
            {},
        )

        if isinstance(status, dict):
            completed = status.get("completed")

            if completed is True:
                return True

            status_str = status.get("status_str")

            if status_str in {
                "success",
                "error",
            }:
                return True

        outputs = history_item.get("outputs")

        return isinstance(outputs, dict) and bool(
            outputs
        )

    def _history_has_error(
        self,
        history_item: dict[str, Any],
    ) -> tuple[bool, str | None]:
        status = history_item.get(
            "status",
            {},
        )

        if not isinstance(status, dict):
            return False, None

        status_str = status.get("status_str")

        if status_str == "error":
            messages = status.get(
                "messages",
                [],
            )

            return (
                True,
                json.dumps(
                    messages,
                    ensure_ascii=False,
                    default=str,
                ),
            )

        messages = status.get(
            "messages",
            [],
        )

        for message in messages:
            if (
                isinstance(message, list)
                and message
                and message[0]
                in {
                    "execution_error",
                    "execution_interrupted",
                }
            ):
                return (
                    True,
                    json.dumps(
                        message,
                        ensure_ascii=False,
                        default=str,
                    ),
                )

        return False, None

    def wait_for_completion(
        self,
        *,
        prompt_id: str,
        client_id: str,
        timeout_seconds: int,
        progress_callback=None,
    ) -> dict[str, Any]:
        started_at = time.monotonic()
        last_history_check = 0.0
        last_progress = 0.0

        ws = None

        try:
            ws = websocket.create_connection(
                self._websocket_url(
                    client_id=client_id,
                ),
                timeout=2,
            )

        except Exception as error:
            logger.warning(
                "ComfyUI WebSocket unavailable; "
                "using history polling: %s",
                error,
            )

        try:
            while True:
                elapsed = (
                    time.monotonic()
                    - started_at
                )

                if elapsed >= timeout_seconds:
                    raise TimeoutError(
                        "ComfyUI prompt exceeded the "
                        f"configured timeout of "
                        f"{timeout_seconds} seconds."
                    )

                if ws is not None:
                    try:
                        raw_message = ws.recv()

                        if isinstance(
                            raw_message,
                            str,
                        ):
                            message = json.loads(
                                raw_message
                            )

                            message_type = (
                                message.get("type")
                            )

                            data = (
                                message.get("data")
                                or {}
                            )

                            message_prompt_id = (
                                data.get("prompt_id")
                            )

                            if (
                                message_prompt_id
                                and str(
                                    message_prompt_id
                                )
                                != prompt_id
                            ):
                                continue

                            if (
                                message_type
                                == "progress"
                            ):
                                value = float(
                                    data.get(
                                        "value",
                                        0,
                                    )
                                )

                                maximum = float(
                                    data.get(
                                        "max",
                                        1,
                                    )
                                    or 1
                                )

                                last_progress = min(
                                    max(
                                        value
                                        / maximum
                                        * 100.0,
                                        0.0,
                                    ),
                                    99.0,
                                )

                                if progress_callback:
                                    progress_callback(
                                        last_progress,
                                        (
                                            "ComfyUI is "
                                            "generating."
                                        ),
                                        {
                                            "node": data.get(
                                                "node"
                                            ),
                                            "value": value,
                                            "max": maximum,
                                        },
                                    )

                            elif (
                                message_type
                                == "executing"
                                and data.get("node")
                                is None
                                and str(
                                    data.get(
                                        "prompt_id"
                                    )
                                )
                                == prompt_id
                            ):
                                break

                            elif message_type in {
                                "execution_error",
                                "execution_interrupted",
                            }:
                                raise RuntimeError(
                                    "ComfyUI execution failed: "
                                    + json.dumps(
                                        data,
                                        ensure_ascii=False,
                                        default=str,
                                    )
                                )

                    except websocket.WebSocketTimeoutException:
                        pass

                    except json.JSONDecodeError:
                        pass

                    except (
                        ConnectionError,
                        OSError,
                        websocket.WebSocketException,
                    ):
                        try:
                            ws.close()
                        except Exception:
                            pass

                        ws = None

                now = time.monotonic()

                if now - last_history_check >= 1.0:
                    last_history_check = now

                    history_item = self.get_history(
                        prompt_id=prompt_id,
                    )

                    if history_item:
                        has_error, error_message = (
                            self._history_has_error(
                                history_item
                            )
                        )

                        if has_error:
                            raise RuntimeError(
                                error_message
                                or (
                                    "ComfyUI execution "
                                    "failed."
                                )
                            )

                        if self._is_history_complete(
                            history_item
                        ):
                            break

                if progress_callback:
                    progress_callback(
                        last_progress,
                        "Waiting for ComfyUI.",
                        {
                            "elapsed_seconds": elapsed,
                        },
                    )

                time.sleep(0.25)

            history_item = self.get_history(
                prompt_id=prompt_id,
            )

            if not history_item:
                raise RuntimeError(
                    "ComfyUI completed the prompt, "
                    "but no history was returned."
                )

            has_error, error_message = (
                self._history_has_error(
                    history_item
                )
            )

            if has_error:
                raise RuntimeError(
                    error_message
                    or "ComfyUI execution failed."
                )

            return history_item

        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def _iter_output_files(
        self,
        history_item: dict[str, Any],
    ):
        outputs = history_item.get(
            "outputs",
            {},
        )

        if not isinstance(outputs, dict):
            return

        supported_groups = (
            "images",
            "gifs",
            "videos",
            "audio",
        )

        for node_id, node_output in outputs.items():
            if not isinstance(
                node_output,
                dict,
            ):
                continue

            for group_name in supported_groups:
                files = node_output.get(
                    group_name,
                    [],
                )

                if not isinstance(files, list):
                    continue

                for file_data in files:
                    if not isinstance(
                        file_data,
                        dict,
                    ):
                        continue

                    filename = file_data.get(
                        "filename"
                    )

                    if not filename:
                        continue

                    yield {
                        "node_id": str(node_id),
                        "group": group_name,
                        "filename": filename,
                        "subfolder": (
                            file_data.get(
                                "subfolder",
                                "",
                            )
                            or ""
                        ),
                        "type": (
                            file_data.get(
                                "type",
                                "output",
                            )
                            or "output"
                        ),
                    }

    def download_output(
        self,
        *,
        file_data: dict[str, Any],
        job_public_id: str,
    ) -> dict[str, Any]:
        query = urlencode(
            {
                "filename": (
                    file_data["filename"]
                ),
                "subfolder": (
                    file_data.get(
                        "subfolder",
                        "",
                    )
                ),
                "type": file_data.get(
                    "type",
                    "output",
                ),
            }
        )

        with httpx.Client(
            timeout=max(
                self._timeout_seconds(),
                120,
            ),
        ) as client:
            response = client.get(
                f"{self._base_url()}/view?"
                f"{query}"
            )

            response.raise_for_status()

            content = response.content
            content_type = response.headers.get(
                "content-type"
            )

        job_directory = (
            self._output_root()
            / job_public_id
        )

        job_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        original_name = Path(
            str(file_data["filename"])
        ).name

        destination = (
            job_directory
            / (
                f"{file_data['node_id']}-"
                f"{uuid4().hex[:8]}-"
                f"{original_name}"
            )
        )

        destination.write_bytes(content)

        local_storage_root = Path(
            str(
                getattr(
                    settings,
                    "LOCAL_STORAGE_DIR",
                    "storage",
                )
            )
        )

        try:
            relative_path = (
                destination
                .relative_to(
                    local_storage_root
                )
                .as_posix()
            )

        except ValueError:
            relative_path = (
                destination.as_posix()
            )

        return {
            **file_data,
            "local_path": str(destination),
            "storage_key": relative_path,
            "public_url": (
                "/local-files/"
                + relative_path
            ),
            "size_bytes": len(content),
            "content_type": content_type,
        }

    def collect_outputs(
        self,
        *,
        history_item: dict[str, Any],
        job_public_id: str,
        download_outputs: bool = True,
    ) -> list[dict[str, Any]]:
        collected: list[
            dict[str, Any]
        ] = []

        for file_data in self._iter_output_files(
            history_item
        ):
            if download_outputs:
                collected.append(
                    self.download_output(
                        file_data=file_data,
                        job_public_id=(
                            job_public_id
                        ),
                    )
                )
            else:
                collected.append(
                    file_data
                )

        return collected

    def execute_queued_prompt(
        self,
        *,
        prompt_id: str,
        client_id: str,
        job_public_id: str,
        timeout_seconds: int,
        download_outputs: bool = True,
        progress_callback=None,
    ) -> dict[str, Any]:
        history_item = self.wait_for_completion(
            prompt_id=prompt_id,
            client_id=client_id,
            timeout_seconds=timeout_seconds,
            progress_callback=progress_callback,
        )

        outputs = self.collect_outputs(
            history_item=history_item,
            job_public_id=job_public_id,
            download_outputs=download_outputs,
        )

        return {
            "success": True,
            "provider": "comfyui_local",
            "prompt_id": prompt_id,
            "client_id": client_id,
            "outputs": outputs,
            "output_count": len(outputs),
            "history": history_item,
        }


comfyui_local_adapter_service = (
    ComfyUILocalAdapterService()
)
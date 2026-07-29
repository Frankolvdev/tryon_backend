from __future__ import annotations

from typing import BinaryIO, Callable


class ProgressReader:
    """Vista limitada de una parte del archivo con telemetría durante read()."""

    def __init__(
        self,
        file: BinaryIO,
        *,
        length: int,
        on_progress: Callable[[int], None],
    ) -> None:
        self._file = file
        self._length = max(0, int(length))
        self._bytes_read = 0
        self._on_progress = on_progress

    def __len__(self) -> int:
        return self._length

    def read(self, size: int = -1) -> bytes:
        remaining = self._length - self._bytes_read
        if remaining <= 0:
            return b""
        if size is None or size < 0 or size > remaining:
            size = remaining
        data = self._file.read(size)
        if not data:
            return b""
        self._bytes_read += len(data)
        self._on_progress(self._bytes_read)
        return data

    def tell(self) -> int:
        return self._bytes_read

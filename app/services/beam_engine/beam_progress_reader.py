from __future__ import annotations

from typing import BinaryIO, Callable

ProgressCallback = Callable[[int], None]


class ProgressReader:
    """Bounded streaming reader for one multipart range.

    Requests consumes this object through ``read()``. The callback receives the
    absolute number of bytes consumed inside this part, allowing progress to be
    measured while the socket is transmitting instead of after a part finishes.
    """

    def __init__(self, file: BinaryIO, *, length: int, on_progress: ProgressCallback):
        self._file = file
        self._length = max(0, int(length))
        self._on_progress = on_progress
        self._bytes_read = 0

    def __len__(self) -> int:
        return self._length

    def tell(self) -> int:
        return self._bytes_read

    def readable(self) -> bool:
        return True

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

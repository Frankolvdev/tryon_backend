from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BeamModelFile:
    source: Path
    relative_path: str
    category: str
    size_bytes: int
    sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeamSyncSummary:
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    bytes_sent: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

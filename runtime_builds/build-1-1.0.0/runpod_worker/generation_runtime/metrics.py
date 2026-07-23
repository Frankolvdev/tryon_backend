from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass
class RuntimeMetricsCollector:
    started_at: float = field(default_factory=monotonic)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add_step(self, *, step_key: str, step_type: str, duration_ms: int, status: str) -> None:
        self.steps.append({
            "step_key": step_key,
            "step_type": step_type,
            "duration_ms": max(int(duration_ms), 0),
            "status": status,
        })

    def snapshot(self) -> dict[str, Any]:
        total_ms = max(int((monotonic() - self.started_at) * 1000), 0)
        workflow_ms = sum(x["duration_ms"] for x in self.steps if x["step_type"] == "workflow")
        python_ms = sum(x["duration_ms"] for x in self.steps if x["step_type"] == "python")
        return {
            "total_duration_ms": total_ms,
            "workflow_duration_ms": workflow_ms,
            "python_duration_ms": python_ms,
            "step_count": len(self.steps),
            "completed_step_count": sum(1 for x in self.steps if x["status"] == "completed"),
            "failed_step_count": sum(1 for x in self.steps if x["status"] == "failed"),
            "steps": list(self.steps),
        }

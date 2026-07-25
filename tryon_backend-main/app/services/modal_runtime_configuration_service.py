from __future__ import annotations

from typing import Any

MODAL_RUNTIME_DEFAULTS: dict[str, Any] = {'profile': '', 'gpu': 'L40S', 'cpu': 8, 'memory_mb': 32768, 'min_containers': 0, 'max_containers': 10, 'container_idle_timeout_seconds': 300, 'execution_timeout_seconds': 900, 'concurrency': 1, 'retries': 2}

def merge_modal_runtime_defaults(config: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(MODAL_RUNTIME_DEFAULTS)
    merged.update(dict(config or {}))
    return merged

def validate_modal_runtime_configuration(
    config: dict[str, Any] | None,
    *,
    token_id_configured: bool,
    token_secret_configured: bool,
) -> list[str]:
    merged = merge_modal_runtime_defaults(config)
    missing: list[str] = []
    required = ('profile', 'gpu', 'cpu', 'memory_mb', 'max_containers',
                'container_idle_timeout_seconds', 'execution_timeout_seconds',
                'concurrency')
    for field in required:
        if merged.get(field) in (None, ''):
            missing.append(field)
    if not token_id_configured:
        missing.append('token_id')
    if not token_secret_configured:
        missing.append('token_secret')
    if int(merged.get('max_containers', 0)) < 1:
        missing.append('max_containers')
    return sorted(set(missing))

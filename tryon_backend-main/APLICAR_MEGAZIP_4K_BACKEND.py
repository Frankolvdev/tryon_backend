from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent

DEFAULTS = {
    "profile": "",
    "gpu": "L40S",
    "cpu": 8,
    "memory_mb": 32768,
    "min_containers": 0,
    "max_containers": 10,
    "container_idle_timeout_seconds": 300,
    "execution_timeout_seconds": 900,
    "concurrency": 1,
    "retries": 2,
}

service = ROOT / "app/services/modal_runtime_configuration_service.py"
service.parent.mkdir(parents=True, exist_ok=True)
service.write_text(
    "from __future__ import annotations\n\n"
    "from typing import Any\n\n"
    f"MODAL_RUNTIME_DEFAULTS: dict[str, Any] = {DEFAULTS!r}\n\n"
    "def merge_modal_runtime_defaults(config: dict[str, Any] | None) -> dict[str, Any]:\n"
    "    merged = dict(MODAL_RUNTIME_DEFAULTS)\n"
    "    merged.update(dict(config or {}))\n"
    "    return merged\n\n"
    "def validate_modal_runtime_configuration(\n"
    "    config: dict[str, Any] | None,\n"
    "    *,\n"
    "    token_id_configured: bool,\n"
    "    token_secret_configured: bool,\n"
    ") -> list[str]:\n"
    "    merged = merge_modal_runtime_defaults(config)\n"
    "    missing: list[str] = []\n"
    "    required = ('profile', 'gpu', 'cpu', 'memory_mb', 'max_containers',\n"
    "                'container_idle_timeout_seconds', 'execution_timeout_seconds',\n"
    "                'concurrency')\n"
    "    for field in required:\n"
    "        if merged.get(field) in (None, ''):\n"
    "            missing.append(field)\n"
    "    if not token_id_configured:\n"
    "        missing.append('token_id')\n"
    "    if not token_secret_configured:\n"
    "        missing.append('token_secret')\n"
    "    if int(merged.get('max_containers', 0)) < 1:\n"
    "        missing.append('max_containers')\n"
    "    return sorted(set(missing))\n",
    encoding="utf-8",
)

changed = [service]
for path in ROOT.rglob("*.py"):
    if ".git" in path.parts or "__pycache__" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    original = text

    if "runpod" not in text.lower():
        continue

    text = re.sub(
        r'Literal\[([^\]]*?"runpod"[^\]]*?)\]',
        lambda m: m.group(0) if '"modal"' in m.group(0)
        else m.group(0)[:-1] + ', "modal"]',
        text,
    )

    if any(word in text.lower() for word in ("seed", "default", "integration")):
        if '"modal"' not in text and "'modal'" not in text:
            match = re.search(
                r'(?P<block>\{\s*["\']provider["\']\s*:\s*["\']runpod["\'].*?\})',
                text,
                re.DOTALL,
            )
            if match:
                block = match.group("block")
                modal = block.replace('"runpod"', '"modal"').replace("'runpod'", "'modal'")
                modal = modal.replace("RunPod", "Modal")
                modal = re.sub(
                    r'(["\']config["\']\s*:\s*)\{.*?\}',
                    lambda m: m.group(1) + json.dumps(DEFAULTS),
                    modal,
                    count=1,
                    flags=re.DOTALL,
                )
                text = text[:match.end()] + ",\n" + modal + text[match.end():]

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        changed.append(path)

print("[4K Backend] Modal agregado con valores recomendados.")
for path in sorted(set(changed)):
    print(" -", path.relative_to(ROOT))

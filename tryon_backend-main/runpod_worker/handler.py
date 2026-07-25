from __future__ import annotations

import runpod

from generation_runtime import GenerationRuntime

runtime = GenerationRuntime()


def handler(job: dict):
    payload = job.get("input") or {}
    return runtime.execute(payload)


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

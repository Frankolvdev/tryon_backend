# TryOn RunPod Generation Runtime

This worker receives one complete Generation Module per RunPod job and executes its ordered `workflow` and `python` steps in the same container.

The image expects ComfyUI to be reachable through `COMFYUI_URL` (default `http://127.0.0.1:8188`). In the production RunPod image, base this worker on the existing ComfyUI image or start ComfyUI before `handler.py`.

Build from repository root:

```bash
docker build -f runpod_worker/Dockerfile -t tryon-generation-runtime:latest .
```

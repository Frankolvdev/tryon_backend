# Mega ZIP 2 — RunPod Generation Runtime

- Dispatches a complete Generation Module as one RunPod job.
- Executes only `workflow` and `python` steps inside the worker container.
- Preserves local and simulated execution behavior.
- Uses runtime contract `tryon.generation-runtime/v1`.
- Includes a standalone RunPod worker and Dockerfile.

The RunPod production image must also contain/start ComfyUI and all project custom nodes/models. `COMFYUI_URL` selects its internal address.

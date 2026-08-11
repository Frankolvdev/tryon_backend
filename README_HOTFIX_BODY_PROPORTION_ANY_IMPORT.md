# Hotfix — missing typing.Any import

Backend-only, minimal fix.

Cause:
- The previous SaveImage-only hotfix added the annotation `dict[str, Any]`.
- `Any` was not imported, causing backend startup to fail with `NameError: name 'Any' is not defined`.

Fix:
- Adds only `from typing import Any` to `app/services/body_proportion_tool_service.py`.
- No logic changes.
- No migrations.
- No changes to storage, billing, jobs, Modal, RunPod, Beam, Runtime Engine, workflow patching, or other generators.

Validation:
- `body_proportion_tool_service.py` compiles successfully.
- `comfyui_local_adapter_service.py` from the previous hotfix also compiles successfully.

Apply:
1. Stop backend.
2. Copy ZIP over backend root.
3. Start backend.

Git:
```
git add .
git commit -m "fix: import Any for body proportion SaveImage filter"
git push
```

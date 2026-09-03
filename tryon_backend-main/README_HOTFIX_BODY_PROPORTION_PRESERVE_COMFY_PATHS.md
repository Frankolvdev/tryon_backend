# Hotfix — Body Proportion Tool preserves ComfyUI workflow paths

Scope:
- Backend only.
- Changes only:
  - app/services/comfyui_local_adapter_service.py
  - app/services/body_proportion_tool_service.py
- No migrations.
- No changes to storage, jobs, billing, Modal, RunPod, Beam, Runtime Engine or other generators.

Behavior:
- Existing callers of queue_prompt keep the current path-normalization behavior.
- The Body Proportion Tool opts into `preserve_workflow_paths=True`.
- Therefore paths such as `Pony\\...` and `Klein\\...` are sent to ComfyUI exactly as stored in the uploaded API workflow.
- Only explicitly mapped inputs are patched by the Body Proportion Tool.

Apply:
1. Stop backend.
2. Copy this ZIP over the backend root.
3. Start backend and regenerate one body-proportion preset.

Git:
git add .
git commit -m "fix: preserve ComfyUI model paths in body proportion tool"
git push

Important:
This hotfix fixes the slash/path mutation. If ComfyUI then reports missing required inputs such as node 22104 `model` or node 22111 `vae`, those are separate workflow-API validation issues and must be corrected in the exported workflow.

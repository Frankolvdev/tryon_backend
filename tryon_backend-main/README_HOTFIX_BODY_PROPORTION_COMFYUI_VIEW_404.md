# Hotfix — Body Proportion ComfyUI image download 404

Backend-only, isolated hotfix.

Problem fixed:
- Body Proportion Tool received valid temporary image metadata from ComfyUI.
- Backend attempted to download it from `/view?...`.
- Current ComfyUI serves these temporary files through `/api/view?...`, producing 404 on `/view`.

Blindage:
- Existing platform callers keep their historical `/view` behavior.
- Only Body Proportion Tool opts into `prefer_api_view=True`.
- For this tool the adapter tries `/api/view` first and falls back to `/view` only on 404.
- filename, subfolder and type are preserved exactly from ComfyUI history.
- No changes to workflow patching, models, storage configuration, billing, jobs, Modal, RunPod, Beam or Runtime Engine.
- No migration required.

Apply:
1. Stop backend.
2. Copy ZIP contents over backend root.
3. Start backend.
4. Regenerate one body-proportion preset.

Git:
git add .
git commit -m "fix: download body proportion outputs from ComfyUI api view endpoint"
git push

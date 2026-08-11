# Hotfix — strict Body Proportion workflow patch

Backend-only, isolated hotfix.

What it does:
- Deep-copies the uploaded ComfyUI API workflow.
- Changes ONLY explicitly configured mapped inputs.
- Refuses to create missing inputs.
- Verifies the patched workflow against the original before submission.
- Aborts if any JSON path outside the configured mappings changed.
- Preserves ComfyUI model/LoRA paths exactly for this tool only.
- Existing callers of the local ComfyUI adapter keep their historical path preprocessing.

No migrations.
No changes to storage, billing, normal jobs, Modal, RunPod, Beam, Runtime Engine, or other generators.

Apply:
1. Stop backend.
2. Copy ZIP contents over backend root.
3. Start backend.
4. Test one body proportion category.

Git:
git add .
git commit -m "fix: strictly patch only mapped ComfyUI inputs for body proportions"
git push

Note:
If ComfyUI still reports a required input missing after this fix, that missing input is already absent from the exact workflow JSON saved in the Body Proportion Tool configuration. This hotfix guarantees the tool itself does not remove it.

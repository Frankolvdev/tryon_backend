# Hotfix — Body Proportion final SaveImage only

Backend-only isolated hotfix.

Root cause:
- The Body Proportion workflow can contain many PreviewImage outputs of type=temp.
- The tool was downloading every output returned by ComfyUI.
- A temporary PreviewImage could already be unavailable, causing a 404 before the final SaveImage was reached.

Fix:
- Body Proportion Tool detects SaveImage nodes in its workflow.
- Exactly one SaveImage is required.
- Only outputs from that node are downloaded for this tool.
- PreviewImage/temp outputs are ignored.
- If zero or multiple SaveImage nodes exist, the tool aborts explicitly instead of guessing.
- Existing ComfyUI adapter behavior remains unchanged for every other caller because the node filter is opt-in.
- The strict workflow patch and path-preservation behavior remain intact.

No migrations.
No changes to storage, billing, normal jobs, Modal, RunPod, Beam, Runtime Engine, or other generators.

Apply:
1. Stop backend.
2. Copy ZIP contents over backend root.
3. Start backend.
4. Regenerate one body proportion preset.

Git:
git add .
git commit -m "fix: collect only final SaveImage output for body proportions"
git push

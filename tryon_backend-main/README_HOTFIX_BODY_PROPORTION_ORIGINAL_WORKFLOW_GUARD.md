# Hotfix — Original ComfyUI workflow guard

Backend-only, isolated hotfix.

What it does:
- Validates the exact API workflow stored by Body Proportions BEFORE applying any mapped values.
- Never infers, creates, repairs, reconnects, normalizes, or removes workflow inputs.
- If a KSampler is already missing model/positive/negative/latent_image, or a VAEDecode is already missing samples/vae, generation is rejected before submission.
- Error includes a SHA256 of the original stored workflow so the source can be identified exactly.
- Existing strict whitelist patch remains: only explicitly mapped inputs may change.
- No changes to any other platform module.

No migrations.

Apply:
1. Stop backend.
2. Copy this ZIP over the backend root.
3. Start backend.
4. Generate one preset.

Git:
git add .
git commit -m "fix: validate original ComfyUI workflow before body proportion patching"
git push

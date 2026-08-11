# Body Proportions combined hotfix

Changes:
- Big Breast: preview-only breasts_size boost +0.2.
- Huge Breast: preview-only breasts_size boost +0.5.
- Persisted breast values remain unchanged.
- Low Fat default fat_thin: 0.8 instead of 1.0.
- ComfyUI history polling: transient connection failures no longer abort after 5 retries; the same prompt_id is polled until the existing configured timeout.

No workflow resubmission. No changes to storage, billing, Modal, RunPod, Beam, Runtime Engine, or unrelated platform behavior.

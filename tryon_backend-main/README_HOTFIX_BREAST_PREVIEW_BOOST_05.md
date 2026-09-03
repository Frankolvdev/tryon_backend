# Hotfix — Preview breast boost +0.5

Corrección mínima del Body Proportion Tool.

Antes:
- Big Breast / Huge Breast enviaban temporalmente `breasts_size + 5.0` a ComfyUI.

Ahora:
- Big Breast / Huge Breast envían temporalmente `breasts_size + 0.5`.

Importante:
- El valor persistido del preset NO cambia.
- Solo cambia el valor temporal usado para generar la preview.
- No toca storage, reglas, categorías, jobs, billing, Modal, RunPod, Beam, Runtime Engine ni otras herramientas.

Git:
git add .
git commit -m "fix: correct breast preview boost from 5.0 to 0.5"
git push

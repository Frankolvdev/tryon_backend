# Body Proportion Matrix V3 — Backend (incremental)

Apply these files over the current backend root.

Changes are isolated to the existing Body Proportion Tool:
- Dynamic fat/glute/breast anchors.
- 6 default body-fat bands (12/18/24/30/36/42% labels).
- Dynamic base matrix (6×4×4 = 96 by default; grows with intermediates).
- Server-side strict anchor ordering and numeric limits.
- Sync removes only obsolete derived base categories and their tool-owned images.
- DELETE /api/v1/admin/tools-generation/body-proportions/reset/{sex}
  deletes only this tool's presets/config/storage links/local mirror for the selected sex.

No existing global storage configuration or commercial generation pipeline is modified.

Commands:
    alembic upgrade heads
    python -m compileall app

Git:
    git add .
    git commit -m "feat: add dynamic body proportion anchors and isolated reset"
    git push

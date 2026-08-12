# Fix — false concurrent generation lock

Base exacta:
tryon_backend-main - 2026-08-11T232506.110.zip

Problem:
The previous guard considered any DB row with status=`generating` to be an
active execution. A crashed/restarted request could leave that state forever,
causing every future generation to return:
"No es posible ejecutar dos generaciones..."

Fix:
- Shared non-blocking in-process lock remains active across Body Proportions
  and Bubble Butt.
- DB `generating` flags are reconciled with ComfyUI `/queue`.
- If ComfyUI has queue_running or queue_pending -> the second generation is blocked.
- If ComfyUI queue is empty -> orphaned `generating` rows are automatically
  recovered to `error`, then the requested generation is allowed to continue.
- If ComfyUI queue lookup itself fails, stale DB state is released; the actual
  queue_prompt call then reports the real ComfyUI connectivity error.
- No UI, formulas, Bubble values, workflows, mappings, storage or library logic changed.

No migration required.
Python AST validation: OK.

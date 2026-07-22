# MegaZIP 52 — Unified AI job orchestration

This increment replaces direct in-process generation dispatch with a provider-aware Redis queue.

## Runtime behavior

- `local_docker`: one backend worker by default. Jobs are serialized before they reach local ComfyUI.
- `runpod_serverless`: several dispatcher workers may submit and monitor remote jobs concurrently. RunPod remains responsible for remote GPU autoscaling and its own infrastructure queue.
- `simulated`: independent queue for tests.
- PostgreSQL remains the durable source of job state and Redis stores dispatch order/deduplication.
- Pending jobs are re-enqueued after a backend restart instead of being marked failed while reading their status.
- Queued jobs can be cancelled before dispatch. Running provider jobs keep their existing provider cancellation path.

## Optional environment settings

```env
GENERATION_LOCAL_WORKERS=1
GENERATION_RUNPOD_DISPATCH_WORKERS=8
GENERATION_SIMULATED_WORKERS=2
GENERATION_QUEUE_BLOCK_SECONDS=2
GENERATION_HEARTBEAT_SECONDS=10
```

For a single local GPU, keep `GENERATION_LOCAL_WORKERS=1`.
`GENERATION_RUNPOD_DISPATCH_WORKERS` is the platform-side safety limit for concurrently submitted/monitored RunPod jobs. RunPod's endpoint configuration still controls maximum remote workers and remote queueing.

No Alembic migration is required because orchestration metadata is stored in the existing execution snapshot JSON.

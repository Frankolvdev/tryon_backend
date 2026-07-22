# MegaZIP 3 - Runtime finalization

This incremental package finalizes the unified Generation Runtime architecture.

## Included
- Runtime metrics for total, workflow, Python and per-step durations.
- RunPod provider timing capture (`executionTime` and `delayTime`) without pretending it is an exact per-job billed cost.
- Runtime/provider metadata persisted on generation executions.
- Provider registry for the currently supported local, RunPod and simulated engines.
- Remote context returned by the worker, preserving intermediate values and files.
- Backward-compatible `tryon.generation-runtime/v1` contract.

No new step types were added. Only `workflow` and `python` are supported.

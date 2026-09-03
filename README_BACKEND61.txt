BACKEND61 — Modal global terminal reconciliation, no per-job polling, no provider retry

Base: tryon_backend-main (59).zip

Production files changed:
- app/services/modal_pipeline_adapter_service.py
- app/services/generation_module_runtime_service.py
- app/services/generation_job_orchestrator_service.py
- app/services/runtime_builder_service.py

Behavior:
- Normal result delivery stays event-driven through FunctionCall.get.aio().
- No 1-second per-execution call-graph polling.
- The existing global reconciler (~30s) runs a bounded terminal-state safety pass.
- INIT_FAILURE / FAILURE / TIMEOUT in the durable call graph are treated as failure.
- If a child/init failure leaves the parent pending, Backend stops the SAME FunctionCall
  so Modal cannot keep provisioning replacement containers.
- No submit/spawn/requeue is performed by reconciliation.
- Generated Modal runtime remains retries=0.
- Engine cache buster updated to runtime-engine-09-disable-dynamic-snapshot-20260903.

Validation performed:
24 passed.

HOTFIX Backend60 — restore event-driven Modal supervision + explicit no provider retries
Base: tryon_backend-main (58).zip supplied by user

Production files changed ONLY:
- app/services/modal_pipeline_adapter_service.py
- app/services/runtime_builder_service.py

Changes:
1. Removes Backend59 per-execution call-graph polling/watch loop.
2. Restores FunctionCall.get.aio(timeout=remaining) as the normal event-driven wait.
3. Transport recovery may only reattach to the SAME persisted FunctionCall ID; it never submit/spawn/requeues a second generation.
4. Generated Modal class now explicitly sets retries=0 so a failed user invocation is not automatically retried by the configured Modal function policy.
5. Runtime Engine cache buster bumped to runtime-engine-08-force-full-residents-20260903.
6. Existing durable recovery, provider_job_id, cancellation, billing, storage and required-image validation are untouched.
7. Local finalization retries are intentionally untouched: they retry DB/storage finalization only and NEVER create another GPU generation.

Validation:
python -m py_compile app/services/modal_pipeline_adapter_service.py app/services/runtime_builder_service.py
pytest -q tests/test_modal_async_wait_runtime.py tests/test_modal_terminal_reconciliation_contract.py tests/test_modal_cancel_recovery_no_retry_contract.py tests/test_backend59_modal_terminal_reconciliation_and_engine07_contract.py
Result: 19 passed

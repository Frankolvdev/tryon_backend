"""Shared generation runtime primitives.

The package is intentionally provider-neutral.  The backend service owns
persistence, billing and provider adapters; this package owns step dispatch and
runtime context semantics so the same contract can later run inside a worker.
"""

from app.services.generation_runtime.context import GenerationRuntimeContext
from app.services.generation_runtime.step_registry import GenerationRuntimeStepRegistry

__all__ = ["GenerationRuntimeContext", "GenerationRuntimeStepRegistry"]

from .metrics import RuntimeMetricsCollector
from .providers import RuntimeProviderDescriptor, RuntimeProviderRegistry

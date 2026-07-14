from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
)


TRYON_REQUESTS_TOTAL = Counter(
    "tryon_generation_requests_total",
    "Total Try-On generation requests.",
    [
        "execution_mode",
        "category",
    ],
)


TRYON_RESULTS_TOTAL = Counter(
    "tryon_generation_results_total",
    "Try-On results grouped by status.",
    [
        "execution_mode",
        "category",
        "status",
    ],
)


TRYON_DURATION_SECONDS = Histogram(
    "tryon_generation_duration_seconds",
    "Total Try-On generation duration.",
    [
        "execution_mode",
        "category",
        "status",
    ],
    buckets=(
        1,
        2.5,
        5,
        10,
        20,
        30,
        60,
        120,
        300,
        600,
        1200,
        1800,
    ),
)


TRYON_ACTIVE_GENERATIONS = Gauge(
    "tryon_active_generations",
    "Current active Try-On generations.",
    [
        "execution_mode",
    ],
)


BILLING_PAYMENTS_TOTAL = Counter(
    "tryon_billing_payments_total",
    "Billing payments grouped by provider and status.",
    [
        "provider",
        "status",
        "currency",
    ],
)


BILLING_PAYMENT_AMOUNT_TOTAL = Counter(
    "tryon_billing_payment_amount_total",
    "Total payment amount in minor currency units.",
    [
        "provider",
        "currency",
        "status",
    ],
)


BILLING_WEBHOOKS_TOTAL = Counter(
    "tryon_billing_webhooks_total",
    "Billing webhooks grouped by provider and result.",
    [
        "provider",
        "event_type",
        "result",
    ],
)


TOKENS_CHARGED_TOTAL = Counter(
    "tryon_tokens_charged_total",
    "Tokens charged for platform operations.",
    [
        "operation",
    ],
)


TOKENS_REFUNDED_TOTAL = Counter(
    "tryon_tokens_refunded_total",
    "Tokens refunded after failed operations.",
    [
        "operation",
        "reason",
    ],
)


PROVIDER_OPERATIONS_TOTAL = Counter(
    "tryon_provider_operations_total",
    "External provider operations.",
    [
        "provider",
        "operation",
        "status",
    ],
)


PROVIDER_OPERATION_DURATION_SECONDS = Histogram(
    "tryon_provider_operation_duration_seconds",
    "External provider operation duration.",
    [
        "provider",
        "operation",
        "status",
    ],
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2.5,
        5,
        10,
        30,
        60,
        120,
        300,
        600,
        1800,
    ),
)


OPERATIONAL_EVENTS_TOTAL = Counter(
    "tryon_operational_events_total",
    "Persistent operational events created.",
    [
        "source",
        "event_type",
        "severity",
    ],
)


OPERATIONAL_EVENTS_UNRESOLVED = Gauge(
    "tryon_operational_events_unresolved",
    "Unresolved operational events grouped by severity.",
    [
        "severity",
    ],
)
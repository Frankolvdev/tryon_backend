from app.observability.business_metrics import (
    BILLING_PAYMENT_AMOUNT_TOTAL,
    BILLING_PAYMENTS_TOTAL,
    BILLING_WEBHOOKS_TOTAL,
    PROVIDER_OPERATIONS_TOTAL,
    PROVIDER_OPERATION_DURATION_SECONDS,
    TOKENS_CHARGED_TOTAL,
    TOKENS_REFUNDED_TOTAL,
    TRYON_ACTIVE_GENERATIONS,
    TRYON_DURATION_SECONDS,
    TRYON_REQUESTS_TOTAL,
    TRYON_RESULTS_TOTAL,
)


class BusinessObservabilityService:
    def tryon_started(
        self,
        *,
        execution_mode: str,
        category: str,
    ) -> None:
        TRYON_REQUESTS_TOTAL.labels(
            execution_mode=execution_mode,
            category=category,
        ).inc()

        TRYON_ACTIVE_GENERATIONS.labels(
            execution_mode=execution_mode
        ).inc()

    def tryon_finished(
        self,
        *,
        execution_mode: str,
        category: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        TRYON_ACTIVE_GENERATIONS.labels(
            execution_mode=execution_mode
        ).dec()

        TRYON_RESULTS_TOTAL.labels(
            execution_mode=execution_mode,
            category=category,
            status=status,
        ).inc()

        TRYON_DURATION_SECONDS.labels(
            execution_mode=execution_mode,
            category=category,
            status=status,
        ).observe(
            max(
                float(duration_seconds),
                0.0,
            )
        )

    def payment_recorded(
        self,
        *,
        provider: str,
        status: str,
        currency: str,
        amount_minor: int,
    ) -> None:
        normalized_currency = (
            currency.lower()
        )

        BILLING_PAYMENTS_TOTAL.labels(
            provider=provider,
            status=status,
            currency=normalized_currency,
        ).inc()

        BILLING_PAYMENT_AMOUNT_TOTAL.labels(
            provider=provider,
            currency=normalized_currency,
            status=status,
        ).inc(
            max(
                int(amount_minor),
                0,
            )
        )

    def billing_webhook(
        self,
        *,
        provider: str,
        event_type: str,
        result: str,
    ) -> None:
        BILLING_WEBHOOKS_TOTAL.labels(
            provider=provider,
            event_type=event_type,
            result=result,
        ).inc()

    def tokens_charged(
        self,
        *,
        operation: str,
        amount: int,
    ) -> None:
        TOKENS_CHARGED_TOTAL.labels(
            operation=operation
        ).inc(
            max(
                int(amount),
                0,
            )
        )

    def tokens_refunded(
        self,
        *,
        operation: str,
        reason: str,
        amount: int,
    ) -> None:
        TOKENS_REFUNDED_TOTAL.labels(
            operation=operation,
            reason=reason,
        ).inc(
            max(
                int(amount),
                0,
            )
        )

    def provider_operation(
        self,
        *,
        provider: str,
        operation: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        PROVIDER_OPERATIONS_TOTAL.labels(
            provider=provider,
            operation=operation,
            status=status,
        ).inc()

        PROVIDER_OPERATION_DURATION_SECONDS.labels(
            provider=provider,
            operation=operation,
            status=status,
        ).observe(
            max(
                float(duration_seconds),
                0.0,
            )
        )


business_observability_service = (
    BusinessObservabilityService()
)
import importlib
import inspect
from pathlib import Path
from typing import Any

from sqlalchemy import inspect as sqlalchemy_inspect


MODULE_CANDIDATES = [
    # Services
    "app.services.billing_service",
    "app.services.subscription_service",
    "app.services.stripe_service",
    "app.services.stripe_checkout_service",
    "app.services.stripe_customer_service",
    "app.services.stripe_webhook_service",
    "app.services.billing_payment_service",
    "app.services.billing_invoice_service",
    "app.services.billing_refund_service",
    "app.services.refund_service",
    "app.services.token_purchase_service",
    "app.services.subscription_plan_service",

    # Repositories
    "app.repositories.billing_repository",
    "app.repositories.billing_payment_repository",
    "app.repositories.billing_invoice_repository",
    "app.repositories.billing_customer_repository",
    "app.repositories.user_subscription_repository",
    "app.repositories.subscription_repository",
    "app.repositories.subscription_plan_repository",
    "app.repositories.token_purchase_repository",

    # Models
    "app.models.billing_customer",
    "app.models.billing_payment",
    "app.models.billing_invoice",
    "app.models.billing_event",
    "app.models.user_subscription",
    "app.models.subscription_plan",
    "app.models.token_purchase",

    # Schemas
    "app.schemas.billing",
    "app.schemas.subscription",
    "app.schemas.subscription_plan",
    "app.schemas.billing_history",
    "app.schemas.token_purchase",

    # Endpoints
    "app.api.v1.endpoints.billing",
    "app.api.v1.endpoints.billing_history",
    "app.api.v1.endpoints.subscription_plans",
    "app.api.v1.endpoints.stripe_webhooks",
    "app.api.v1.endpoints.admin.subscriptions",
    "app.api.v1.endpoints.admin.billing_payments",
    "app.api.v1.endpoints.admin.billing_invoices",
    "app.api.v1.endpoints.admin.billing_operations",
]


OUTPUT_FILE = Path(
    "commercial_module_report.txt"
)


def is_project_object(
    value: Any,
) -> bool:
    module_name = getattr(
        value,
        "__module__",
        "",
    )

    return isinstance(
        module_name,
        str,
    ) and module_name.startswith(
        "app."
    )


def safe_signature(
    value: Any,
) -> str:
    try:
        return str(
            inspect.signature(value)
        )

    except (
        TypeError,
        ValueError,
    ):
        return "(signature unavailable)"


def describe_function(
    name: str,
    value: Any,
) -> list[str]:
    return [
        f"    FUNCTION: {name}{safe_signature(value)}",
    ]


def describe_class(
    name: str,
    value: type,
) -> list[str]:
    lines = [
        f"    CLASS: {name}",
    ]

    try:
        mapper = sqlalchemy_inspect(
            value,
            raiseerr=False,
        )

    except Exception:
        mapper = None

    if mapper is not None:
        lines.append(
            "      SQLALCHEMY COLUMNS:"
        )

        for column in mapper.columns:
            column_type = str(
                column.type
            )

            lines.append(
                "        - "
                f"{column.key}: "
                f"{column_type}, "
                f"nullable={column.nullable}, "
                f"primary_key={column.primary_key}"
            )

        if mapper.relationships:
            lines.append(
                "      RELATIONSHIPS:"
            )

            for relationship in (
                mapper.relationships
            ):
                lines.append(
                    "        - "
                    f"{relationship.key} -> "
                    f"{relationship.mapper.class_.__name__}"
                )

    methods = []

    for method_name, method in (
        inspect.getmembers(
            value,
            predicate=inspect.isfunction,
        )
    ):
        if method_name.startswith("_"):
            continue

        methods.append(
            f"        - "
            f"{method_name}"
            f"{safe_signature(method)}"
        )

    if methods:
        lines.append(
            "      PUBLIC METHODS:"
        )

        lines.extend(methods)

    annotations = getattr(
        value,
        "__annotations__",
        {},
    )

    if annotations and mapper is None:
        lines.append(
            "      ANNOTATIONS:"
        )

        for field_name, field_type in (
            annotations.items()
        ):
            lines.append(
                "        - "
                f"{field_name}: {field_type}"
            )

    model_fields = getattr(
        value,
        "model_fields",
        None,
    )

    if model_fields:
        lines.append(
            "      PYDANTIC FIELDS:"
        )

        for field_name, field in (
            model_fields.items()
        ):
            lines.append(
                "        - "
                f"{field_name}: "
                f"{field.annotation}, "
                f"required={field.is_required()}"
            )

    return lines


def describe_instance(
    name: str,
    value: Any,
) -> list[str]:
    lines = [
        "    INSTANCE: "
        f"{name} "
        f"({value.__class__.__name__})"
    ]

    methods = []

    for method_name, method in (
        inspect.getmembers(
            value,
            predicate=callable,
        )
    ):
        if method_name.startswith("_"):
            continue

        if not is_project_object(method):
            continue

        methods.append(
            "        - "
            f"{method_name}"
            f"{safe_signature(method)}"
        )

    if methods:
        lines.append(
            "      PUBLIC METHODS:"
        )

        lines.extend(methods)

    return lines


def inspect_module(
    module_name: str,
) -> list[str]:
    lines = [
        "=" * 80,
        f"MODULE: {module_name}",
    ]

    try:
        module = importlib.import_module(
            module_name
        )

    except ModuleNotFoundError as error:
        missing_name = getattr(
            error,
            "name",
            "",
        )

        if (
            missing_name == module_name
            or module_name.startswith(
                f"{missing_name}."
            )
        ):
            lines.append(
                "STATUS: NOT FOUND"
            )

        else:
            lines.append(
                "STATUS: IMPORT ERROR"
            )

            lines.append(
                f"ERROR: {error}"
            )

        return lines

    except Exception as error:
        lines.append(
            "STATUS: IMPORT ERROR"
        )

        lines.append(
            f"ERROR TYPE: "
            f"{type(error).__name__}"
        )

        lines.append(
            f"ERROR: {error}"
        )

        return lines

    lines.append(
        "STATUS: FOUND"
    )

    found_objects = False

    for name, value in sorted(
        vars(module).items()
    ):
        if name.startswith("_"):
            continue

        if inspect.isclass(value):
            if not is_project_object(value):
                continue

            found_objects = True

            lines.extend(
                describe_class(
                    name,
                    value,
                )
            )

            continue

        if inspect.isfunction(value):
            if not is_project_object(value):
                continue

            found_objects = True

            lines.extend(
                describe_function(
                    name,
                    value,
                )
            )

            continue

        if (
            value is not None
            and is_project_object(
                value.__class__
            )
        ):
            found_objects = True

            lines.extend(
                describe_instance(
                    name,
                    value,
                )
            )

    router = getattr(
        module,
        "router",
        None,
    )

    if router is not None:
        found_objects = True

        lines.append(
            "    ROUTES:"
        )

        for route in getattr(
            router,
            "routes",
            [],
        ):
            methods = sorted(
                getattr(
                    route,
                    "methods",
                    [],
                )
                or []
            )

            path = getattr(
                route,
                "path",
                "(unknown)"
            )

            name = getattr(
                route,
                "name",
                "(unnamed)"
            )

            lines.append(
                "        - "
                f"{','.join(methods)} "
                f"{path} "
                f"[{name}]"
            )

    if not found_objects:
        lines.append(
            "    No project objects detected."
        )

    return lines


def main() -> None:
    report_lines = [
        "AI VIRTUAL TRY-ON PLATFORM",
        "COMMERCIAL MODULE INSPECTION",
        "",
    ]

    for module_name in MODULE_CANDIDATES:
        report_lines.extend(
            inspect_module(
                module_name
            )
        )

        report_lines.append("")

    report = "\n".join(
        report_lines
    )

    OUTPUT_FILE.write_text(
        report,
        encoding="utf-8",
    )

    print(report)

    print()
    print(
        f"REPORT SAVED TO: "
        f"{OUTPUT_FILE.resolve()}"
    )


if __name__ == "__main__":
    main()
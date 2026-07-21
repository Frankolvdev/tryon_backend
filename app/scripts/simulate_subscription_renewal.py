from __future__ import annotations

import argparse
from datetime import datetime, timezone

from app.core.config import settings
from app.db.database import SessionLocal
from app.services.subscription_service import subscription_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Credit one subscription period using the production token "
            "allocation logic. Intended for local/test environments."
        )
    )
    parser.add_argument(
        "--subscription-id",
        type=int,
        required=True,
        help="Internal user_subscriptions.id value.",
    )
    parser.add_argument(
        "--reference-id",
        default=None,
        help=(
            "Idempotency reference. Omit it to generate a unique simulated "
            "invoice reference. Reusing a reference will not credit twice."
        ),
    )
    return parser.parse_args()


def main() -> None:
    if settings.APP_ENV.lower() not in {"development", "test", "testing", "local"}:
        raise SystemExit(
            "This command is disabled outside development/test environments."
        )

    args = parse_args()
    reference_id = args.reference_id or (
        "simulated-renewal-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )

    with SessionLocal() as db:
        subscription = subscription_service.grant_period_tokens_if_needed(
            db,
            subscription_id=args.subscription_id,
            reference_id=reference_id,
        )
        metadata = subscription_service._parse_json(
            subscription.metadata_json
        )
        print(
            "Renewal simulation completed: "
            f"subscription_id={subscription.id}, "
            f"user_id={subscription.user_id}, "
            f"reference_id={reference_id}, "
            f"tokens_granted={metadata.get('last_token_grant_amount', 0)}"
        )


if __name__ == "__main__":
    main()

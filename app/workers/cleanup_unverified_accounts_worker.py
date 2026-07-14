import argparse
import json
import logging

from app.db.database import SessionLocal
from app.services.unverified_account_cleanup_service import (
    unverified_account_cleanup_service,
)


logger = logging.getLogger(
    "app.workers.cleanup_unverified_accounts"
)


def run_cleanup(
    *,
    dry_run: bool,
    limit: int,
) -> dict:
    db = SessionLocal()

    try:
        result = (
            unverified_account_cleanup_service
            .cleanup(
                db,
                dry_run=dry_run,
                limit=limit,
            )
        )

        return result.model_dump(
            mode="json"
        )

    except Exception:
        db.rollback()

        logger.exception(
            "Unverified account cleanup failed."
        )

        raise

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deactivate expired unverified "
            "user accounts."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply the cleanup. Without this "
            "flag only a simulation is executed."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help=(
            "Maximum number of accounts "
            "processed in one execution."
        ),
    )

    arguments = parser.parse_args()

    if arguments.limit < 1:
        raise ValueError(
            "The cleanup limit must be "
            "greater than zero."
        )

    result = run_cleanup(
        dry_run=not arguments.apply,
        limit=arguments.limit,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
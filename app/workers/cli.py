import argparse
import logging

from app.workers.background_worker import (
    BackgroundWorker,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a persistent background worker."
        )
    )

    parser.add_argument(
        "--queue",
        default="default",
        help="Queue name consumed by the worker.",
    )

    parser.add_argument(
        "--name",
        default=None,
        help="Unique worker name.",
    )

    parser.add_argument(
        "--version",
        default="1.0.0",
        help="Worker version.",
    )

    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=120,
    )

    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=15,
    )

    parser.add_argument(
        "--redis-wait-seconds",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(
            logging,
            args.log_level.upper(),
            logging.INFO,
        ),
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        ),
    )

    worker = BackgroundWorker(
        queue_name=args.queue,
        worker_name=args.name,
        worker_version=args.version,
        lease_seconds=args.lease_seconds,
        heartbeat_seconds=(
            args.heartbeat_seconds
        ),
        redis_wait_seconds=(
            args.redis_wait_seconds
        ),
        poll_seconds=args.poll_seconds,
    )

    worker.run_forever()


if __name__ == "__main__":
    main()
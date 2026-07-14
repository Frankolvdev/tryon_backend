import json
import sys
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:8001"


def request(
    path: str,
) -> tuple[int, str, dict]:
    request_object = urllib.request.Request(
        BASE_URL + path,
        headers={
            "X-Correlation-ID": (
                "observability-test-script"
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request_object,
            timeout=15,
        ) as response:
            body = response.read().decode(
                "utf-8"
            )

            headers = dict(
                response.headers.items()
            )

            return (
                response.status,
                body,
                headers,
            )

    except urllib.error.HTTPError as error:
        body = error.read().decode(
            "utf-8"
        )

        return (
            error.code,
            body,
            dict(error.headers.items()),
        )


def assert_condition(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    results: list[dict] = []

    status_code, body, headers = request(
        "/api/v1/health/live"
    )

    assert_condition(
        status_code == 200,
        "Liveness endpoint did not return 200.",
    )

    liveness = json.loads(body)

    assert_condition(
        liveness.get("status") == "alive",
        "Liveness response is invalid.",
    )

    results.append(
        {
            "test": "liveness",
            "success": True,
        }
    )

    status_code, body, headers = request(
        "/api/v1/health/ready"
    )

    assert_condition(
        status_code == 200,
        "Readiness endpoint did not return 200.",
    )

    readiness = json.loads(body)

    assert_condition(
        readiness.get("ready") is True,
        "Application is not ready.",
    )

    results.append(
        {
            "test": "readiness",
            "success": True,
        }
    )

    status_code, body, headers = request(
        "/api/v1/metrics"
    )

    assert_condition(
        status_code == 200,
        "Metrics endpoint did not return 200.",
    )

    assert_condition(
        "tryon_http_requests_total" in body,
        "HTTP request metric is missing.",
    )

    assert_condition(
        "tryon_postgres_available" in body,
        "PostgreSQL metric is missing.",
    )

    assert_condition(
        "tryon_redis_available" in body,
        "Redis metric is missing.",
    )

    results.append(
        {
            "test": "prometheus_metrics",
            "success": True,
        }
    )

    status_code, body, headers = request(
        "/api/v1/health"
    )

    assert_condition(
        status_code == 200,
        "Basic health endpoint failed.",
    )

    correlation_id = (
        headers.get("X-Correlation-ID")
        or headers.get("x-correlation-id")
    )

    assert_condition(
        correlation_id
        == "observability-test-script",
        "Correlation ID was not preserved.",
    )

    results.append(
        {
            "test": "correlation_id",
            "success": True,
        }
    )

    print(
        json.dumps(
            {
                "success": True,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())

    except Exception as error:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(error),
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        sys.exit(1)
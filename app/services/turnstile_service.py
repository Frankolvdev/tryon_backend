import logging
import os

import httpx

from app.common.exceptions import (
    ForbiddenException,
)


logger = logging.getLogger(
    "app.turnstile"
)


class TurnstileService:
    VERIFY_URL = (
        "https://challenges.cloudflare.com/"
        "turnstile/v0/siteverify"
    )

    def _secret_key(
        self,
    ) -> str:
        return os.getenv(
            "TURNSTILE_SECRET_KEY",
            "",
        ).strip()

    def verify(
        self,
        *,
        token: str | None,
        remote_ip: str | None,
    ) -> None:
        secret_key = self._secret_key()

        if not secret_key:
            raise RuntimeError(
                "TURNSTILE_SECRET_KEY "
                "is not configured."
            )

        if not token:
            raise ForbiddenException(
                "Turnstile validation is required."
            )

        payload = {
            "secret": secret_key,
            "response": token,
        }

        if remote_ip:
            payload["remoteip"] = remote_ip

        try:
            response = httpx.post(
                self.VERIFY_URL,
                data=payload,
                timeout=10.0,
            )

            response.raise_for_status()

            result = response.json()

        except Exception as error:
            logger.exception(
                "Turnstile verification request failed."
            )

            raise ForbiddenException(
                "Human verification could not "
                "be completed."
            ) from error

        if not bool(
            result.get("success")
        ):
            logger.warning(
                "Turnstile rejected registration.",
                extra={
                    "error_codes": (
                        result.get(
                            "error-codes",
                            [],
                        )
                    ),
                },
            )

            raise ForbiddenException(
                "Human verification failed."
            )


turnstile_service = TurnstileService()
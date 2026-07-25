from typing import Any


class LocalizedApplicationException(
    Exception
):
    status_code = 400
    translation_key = "common.error"

    def __init__(
        self,
        *,
        translation_key: str | None = None,
        variables: dict[str, Any] | None = None,
        default_message: str | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ):
        self.translation_key = (
            translation_key
            or self.translation_key
        )

        self.variables = variables or {}

        self.default_message = (
            default_message
            or self.translation_key
        )

        self.status_code = (
            status_code
            or self.status_code
        )

        self.error_code = (
            error_code
            or self.translation_key
        )

        super().__init__(
            self.default_message
        )


class LocalizedBadRequestException(
    LocalizedApplicationException
):
    status_code = 400


class LocalizedUnauthorizedException(
    LocalizedApplicationException
):
    status_code = 401
    translation_key = (
        "auth.login_required"
    )


class LocalizedForbiddenException(
    LocalizedApplicationException
):
    status_code = 403


class LocalizedNotFoundException(
    LocalizedApplicationException
):
    status_code = 404


class LocalizedConflictException(
    LocalizedApplicationException
):
    status_code = 409


class LocalizedTooManyRequestsException(
    LocalizedApplicationException
):
    status_code = 429
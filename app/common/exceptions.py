class AppException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "APP_ERROR",
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found."):
        super().__init__(
            message=message,
            status_code=404,
            error_code="NOT_FOUND",
        )


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized."):
        super().__init__(
            message=message,
            status_code=401,
            error_code="UNAUTHORIZED",
        )


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden."):
        super().__init__(
            message=message,
            status_code=403,
            error_code="FORBIDDEN",
        )


class ConflictException(AppException):
    def __init__(self, message: str = "Conflict."):
        super().__init__(
            message=message,
            status_code=409,
            error_code="CONFLICT",
        )
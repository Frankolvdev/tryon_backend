from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    success: bool = False
    error_code: str
    message: str


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = "Success."
    data: Any | None = None
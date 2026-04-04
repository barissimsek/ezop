from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., examples=["INVALID_API_KEY"])
    message: str = Field(..., examples=["The provided API key is invalid."])


class BaseResponse(BaseModel):
    """
    Standard response envelope for all API endpoints.

    Every response — success or error — shares this shape so the SDK
    can always parse the same structure without branching on content type.
    """

    success: bool
    data: Any = None
    error: ErrorDetail | None = None
    request_id: str = Field(default_factory=lambda: str(uuid4()))

    @classmethod
    def ok(cls, data: Any) -> "BaseResponse":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, code: str, message: str) -> "BaseResponse":
        return cls(success=False, error=ErrorDetail(code=code, message=message))

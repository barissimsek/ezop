from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse[T](BaseModel):
    success: bool
    data: T | None
    error: ErrorDetail | None

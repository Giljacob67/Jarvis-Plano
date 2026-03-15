from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


class NotImplementedResponse(BaseModel):
    status: str = "not_implemented"
    message: str

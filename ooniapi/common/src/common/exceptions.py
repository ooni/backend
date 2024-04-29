from typing import Dict

from fastapi import HTTPException


class BaseOONIException(HTTPException):
    def __init__(self, detail: str, headers: Dict | None):
        super.__init__(status_code=400, detail=detail, headers=headers)


class InvalidRequest(BaseOONIException):
    def __init__(self):
        super().__init__(detail="invalid parameters in the request")


class OwnershipPermissionError(BaseOONIException):
    def __init__(self):
        super().__init__(
            detail = "attempted to create, update or delete an item belonging to another user"
        )


class DatabaseQueryError(BaseOONIException):
    def __init__(self):
        super().__init__(detail="")

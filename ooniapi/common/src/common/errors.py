"""
API errors with support for localization

"""

from typing import Dict, Optional
from pydantic import Field
from fastapi import HTTPException


class BaseOONIException(HTTPException):
    """Custom exception class for OONI-related errors."""

    def __init__(
        self,
        description: Optional[str] = Field(
            default="Generic OONI error",
            description="Error description"
        ),
        err_args: Optional[Dict[str, str]] = Field(
            default={},
            description="Additional error arguments"
        ),
        err_str: str = Field(
            default="err_generic_ooni_exception",
            description="Error string"
        ),
        code: int = Field(
            default=400,
            description="Error code"
        ),
    ):
        """
        Initialize the BaseOONIException.

        Args:
            description (Optional[str]): A description of the error.
            err_args (Optional[Dict[str, str]]): Additional arguments related to the error.
            err_str (str): An error string identifier.
            code (int): HTTP status code associated with the error.
        """
        super().__init__(status_code=code, detail=description)
        self.err_args = err_args
        self.err_str = err_str
        self.description = description


class BadURL(BaseOONIException):
    """Exception raised for invalid URLs."""
    err_str = "err_bad_url"
    description = "Invalid URL"


class BadCategoryCode(BaseOONIException):
    """Exception raised for invalid category codes."""
    err_str = "err_bad_category_code"
    description = "Invalid category code"


class BadCategoryDescription(BaseOONIException):
    """Exception raised for invalid category descriptions."""
    err_str = "err_bad_category_description"
    description = "Invalid category description"


class BadDate(BaseOONIException):
    """Exception raised for invalid date formats."""
    err_str = "err_bad_date"
    description = "Invalid date"


class CountryNotSupported(BaseOONIException):
    """Exception raised when a country is not supported."""
    err_str = "err_country_not_supported"
    description = "Country Not Supported"


class InvalidCountryCode(BaseOONIException):
    """Exception raised for invalid country codes."""
    err_str = "err_invalid_country_code"
    description = "Country code is invalid"


class EmptyTranslation(BaseOONIException):
    """Exception raised for empty translation fields."""
    err_str = "err_empty_translation_field"
    description = "Empty translation field"


class DuplicateURLError(BaseOONIException):
    """Exception raised for duplicate URLs."""
    err_str = "err_duplicate_url"
    description = "Duplicate URL"


class DuplicateRuleError(BaseOONIException):
    """Exception raised for duplicate rules."""
    err_str = "err_duplicate_rule"
    description = "Duplicate rule"


class RuleNotFound(BaseOONIException):
    """Exception raised when a rule is not found."""
    code = 404
    err_str = "err_rule_not_found"
    description = "Rule not found error"


class CannotClosePR(BaseOONIException):
    """Exception raised when unable to close a pull request (PR)."""
    err_str = "err_cannot_close_pr"
    description = "Unable to close PR. Please reload data."


class CannotUpdateList(BaseOONIException):
    """Exception raised when unable to update due to changes in the URL list."""
    err_str = "err_cannot_update_list"
    description = "Unable to update. The URL list has changed in the meantime."


class NoProposedChanges(BaseOONIException):
    """Exception raised when there are no proposed changes."""
    err_str = "err_no_proposed_changes"
    description = "No changes are being proposed"


class OwnershipPermissionError(BaseOONIException):
    """Exception raised for ownership permission errors."""
    err_str = "err_ownership"
    description = "Attempted to create, update, or delete an item belonging to another user."


class InvalidRequest(BaseOONIException):
    """Exception raised for invalid parameters in a request."""
    err_str = "err_request_params"
    description = "Invalid parameters in the request"

"""
API errors with support for localization

"""

from typing import Dict, Optional
from pydantic import Field
from fastapi import HTTPException


class BaseOONIException(HTTPException):
    """Custom exception class for OONI-related errors."""

    status_code: int = 400
    err_str: str = "err_generic_ooni_exception"
    err_args: Optional[Dict[str, str]] = None
    description: str = "Generic OONI error"

    def __init__(
        self,
        description: Optional[str] = None,
        err_args: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the BaseOONIException.

        Args:
            description (Optional[str]): A description of the error.
            err_args (Optional[Dict[str, str]]): Additional arguments related to the error.
        """
        if description != None:
            self.description = description
        if err_args != None:
            self.err_args = err_args

        super().__init__(
            status_code=self.status_code,
            detail={
                "description": self.description,
                "err_args": self.err_args,
                "err_str": self.err_str,
            },
        )


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


class InvalidPullRequestState(BaseOONIException):
    """Exception raised when a stored pr_id looks malformed, or GitHub's
    response about a PR's status doesn't have the expected shape. Either
    indicates something is wrong with the PR-tracking state for this
    account, not just a normal request-validation failure."""

    err_str = "err_invalid_pr_state"
    description = "The tracked pull request state is invalid or malformed"


class CannotProposeChanges(BaseOONIException):
    """Exception raised when pushing the branch or opening the PR on
    GitHub fails (e.g. a transient network/GitHub outage). Retrying is
    expected to work once the underlying issue clears - the change
    itself is not lost even if the push succeeded but opening the PR
    failed, since submit() can simply be called again."""

    err_str = "err_cannot_propose_changes"
    description = "Unable to submit changes. Please try again."


class NoProposedChanges(BaseOONIException):
    """Exception raised when there are no proposed changes."""

    err_str = "err_no_proposed_changes"
    description = "No changes are being proposed"


class OwnershipPermissionError(BaseOONIException):
    """Exception raised for ownership permission errors."""

    err_str = "err_ownership"
    description = (
        "Attempted to create, update, or delete an item belonging to another user."
    )


class InvalidRequest(BaseOONIException):
    """Exception raised for invalid parameters in a request."""

    err_str = "err_request_params"
    description = "Invalid parameters in the request"

class AddressNotFoundError(Exception):
    """Exception raised for IP not found in geolookup database"""

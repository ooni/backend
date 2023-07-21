"""
API errors with support for localization

"""

from typing import Dict, Optional

from flask import make_response, jsonify
from werkzeug.exceptions import HTTPException


class BaseOONIException(HTTPException):
    code: int = 400
    err_str: str = "err_generic_ooni_exception"
    err_args: Optional[Dict[str, str]] = None
    description: str = "Generic OONI error"

    def __init__(
        self,
        description: Optional[str] = None,
        err_args: Optional[Dict[str, str]] = None,
    ):
        super().__init__(description=description)
        if err_args is not None:
            self.err_args = err_args


class BadURL(BaseOONIException):
    err_str = "err_bad_url"
    description = "Invalid URL"


class BadCategoryCode(BaseOONIException):
    err_str = "err_bad_category_code"
    description = "Invalid category code"


class BadCategoryDescription(BaseOONIException):
    err_str = "err_bad_category_description"
    description = "Invalid category description"


class BadDate(BaseOONIException):
    err_str = "err_bad_date"
    description = "Invalid date"


class CountryNotSupported(BaseOONIException):
    err_str = "err_country_not_supported"
    description = "Country Not Supported"


class InvalidCountryCode(BaseOONIException):
    err_str = "err_invalid_country_code"
    description = "Country code is invalid"


class EmptyTranslation(BaseOONIException):
    err_str = "err_empty_translation_field"
    description = "Empty translation field"


class DuplicateURLError(BaseOONIException):
    err_str = "err_duplicate_url"
    description = "Duplicate URL"


class DuplicateRuleError(BaseOONIException):
    err_str = "err_duplicate_rule"
    description = "Duplicate rule"


class RuleNotFound(BaseOONIException):
    code = 404
    err_str = "err_rule_not_found"
    description = "Rule not found error"


class CannotClosePR(BaseOONIException):
    err_str = "err_cannot_close_pr"
    description = "Unable to close PR. Please reload data."


class CannotUpdateList(BaseOONIException):
    err_str = "err_cannot_update_list"
    description = "Unable to update. The URL list has changed in the meantime."


class NoProposedChanges(BaseOONIException):
    err_str = "err_no_proposed_changes"
    description = "No changes are being proposed"


class OwnershipPermissionError(BaseOONIException):
    err_str = "err_ownership"
    description = (
        "Attempted to create, update or delete an item beloging to another user"
    )


class InvalidRequest(BaseOONIException):
    err_str = "err_request_params"
    description = "Invalid parameters in the request"


def jerror(err, code=400):
    if isinstance(err, BaseOONIException):
        err_j = {
            "error": err.description,
            "err_str": err.err_str,
        }
        if err.err_args:
            err_j["err_args"] = err.err_args
        return make_response(jsonify(err_j), err.code)

    return make_response(jsonify(error=str(err)), code)

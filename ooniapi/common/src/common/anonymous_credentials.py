from typing import Self
from enum import Enum

# Use this enum to translate from the DB model format to the API version and
# backwards
class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNVERIFIED = "unverified"

    @property
    def code(self) -> str:
        return {
            VerificationStatus.VERIFIED: "t",
            VerificationStatus.FAILED: "f",
            VerificationStatus.UNVERIFIED: "u",
        }[self]

    @classmethod
    def from_code(cls, code: str) -> Self:
        return {
            "t": VerificationStatus.VERIFIED,
            "f": VerificationStatus.FAILED,
            "u": VerificationStatus.UNVERIFIED,
        }[code]

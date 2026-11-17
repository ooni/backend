# This module implements token-based authentication for the API, not to confuse
# with user authentication for oonirun.
#
# These are fundamentally two different families of users.
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from ..postgresql import Base
from ..models import UtcDateTime


class ApiToken(Base):
    """
    Tokens used to access the API with different rate limits
    """

    __tablename__ = "apitoken"

    # sha256 hex digest of the token.
    # The token itself is never stored.
    token_hash: Mapped[str] = mapped_column(sa.String(64), primary_key=True)

    date_created: Mapped[datetime] = mapped_column(
        UtcDateTime(), server_default=sa.func.now()
    )

    # NULL = token never expires. Revoking a token sets this to now()
    expires_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime())

    # Public identifier of the token owner.
    # We don't have an user model at the moment
    user_id: Mapped[str] = mapped_column(index=True)

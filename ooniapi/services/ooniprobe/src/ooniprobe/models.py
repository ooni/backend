from datetime import datetime
from typing import Self, Dict, Any
from .common.models import UtcDateTime
from .common.postgresql import Base
from sqlalchemy import ForeignKey, Sequence, String, func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column, relationship, Session, joinedload
from sqlalchemy import desc
from ooniauth_py import ServerState
import logging
log = logging.getLogger(__name__)


class OONIProbeVPNProvider(Base):
    __tablename__ = "ooniprobe_vpn_provider"

    id: Mapped[str] = mapped_column(
        String,
        Sequence("ooniprobe_vpn_provider_id_seq", start=1),
        primary_key=True,
        nullable=False,
    )
    date_updated: Mapped[datetime] = mapped_column(UtcDateTime())
    date_created: Mapped[datetime] = mapped_column(UtcDateTime())

    provider_name: Mapped[str] = mapped_column()

    openvpn_cert: Mapped[str] = mapped_column(nullable=True)
    openvpn_ca: Mapped[str] = mapped_column(nullable=True)
    openvpn_key: Mapped[str] = mapped_column(nullable=True)

    endpoints = relationship("OONIProbeVPNProviderEndpoint", back_populates="provider")


class OONIProbeVPNProviderEndpoint(Base):
    __tablename__ = "ooniprobe_vpn_provider_endpoint"

    id: Mapped[str] = mapped_column(
        String,
        Sequence("ooniprobe_vpn_provider_endpoint_id_seq", start=1),
        primary_key=True,
        nullable=False,
    )
    date_updated: Mapped[datetime] = mapped_column(UtcDateTime())
    date_created: Mapped[datetime] = mapped_column(UtcDateTime())

    protocol: Mapped[str] = mapped_column()
    address: Mapped[str] = mapped_column()
    transport: Mapped[str] = mapped_column()
    # TODO: maybe we want this in the future to store location and other
    # metadata about an endpoint
    # metadata: Mapped[Dict[str, str]] = mapped_column(nullable=True)

    provider_id = mapped_column(ForeignKey("ooniprobe_vpn_provider.id"))
    provider = relationship("OONIProbeVPNProvider", back_populates="endpoints")


class OONIProbeServerState(Base):
    """
    Server state used for the anonymous credentials protocol.
    Stores public parameters and secret key used for credential
    generation and validation
    """

    __tablename__ = "ooniprobe_server_state"

    id: Mapped[str] = mapped_column(
        String,
        Sequence("ooniprobe_server_state_id_seq", start=1),
        primary_key=True,
        nullable=False,
    )
    date_created: Mapped[datetime] = mapped_column(UtcDateTime(), default=func.now())
    secret_key: Mapped[str] = mapped_column()
    public_parameters: Mapped[str] = mapped_column()

    @classmethod
    def make_new_state(cls, session: Session, state : ServerState | None = None) -> Self:
        """
        Creates a new state, saving it to db
        If no state value is provided, create a default one with random values
        """
        if state is None:
            state = ServerState()

        new = cls(
            secret_key=state.get_secret_key(),
            public_parameters = state.get_public_parameters()
            )
        session.add(new)
        session.commit()
        session.refresh(new)

        return new

    def to_protocol(self) -> ServerState:
        """
        Converts this instance into a protocol object
        """

        return ServerState.from_creds(self.public_parameters, self.secret_key)

    @classmethod
    def init_table(cls, session: Session):
        """
        Creates a new entry if none exists.
        """
        entry = session.query(cls).limit(1).one_or_none()
        if entry is None:
            log.info("No OONIProbeServerState entry found. Creating a new one...")
            cls.make_new_state(session)
        else:
            log.info("OONIProbeServerState already initialized!")


class OONIProbeManifest(Base):
    """
    Manifest used to share with clients the information they need to provide
    registration and validation of measurement submissions
    """

    __tablename__ = "ooniprobe_manifest"

    version: Mapped[str] = mapped_column(
        String,
        Sequence("ooniprobe_manifest_id_seq", start=1),
        primary_key=True,
        nullable=False,
    )
    date_created: Mapped[datetime] = mapped_column(UtcDateTime(), default=func.now())
    nym_scope: Mapped[str] = mapped_column(default="ooni.org/{probe_cc}/{probe_asn}")
    submission_policy: Mapped[Dict[str, Any]] = mapped_column(default={})

    server_state_id = mapped_column(ForeignKey("ooniprobe_server_state.id"))
    server_state = relationship("OONIProbeServerState")

    @classmethod
    def get_latest(cls, session: Session) -> Self | None:
        return (
            session
            .query(cls)
            .options(joinedload(cls.server_state))
            .order_by(desc(cls.version))
            .limit(1)
            .one_or_none()
        )

    @classmethod
    def get_by_version(cls, session: Session, version: str) -> Self | None:
        return (
            session
            .query(cls)
            .options(joinedload(cls.server_state))
            .where(cls.version == version)
            .one_or_none()
        )

    @classmethod
    def init_table(cls, session: Session):
        """
        Creates a new manifest entry if none exists
        """
        entry = session.query(cls).limit(1).one_or_none()
        if entry is None:
            log.info("No OONIProbeManifest entry found. Creating a new one...")

            # Make sure there's a server state
            OONIProbeServerState.init_table(session)
            state = session.query(OONIProbeServerState).order_by(desc(OONIProbeServerState.date_created)).limit(1).one()
            entry = cls(server_state_id=state.id)
            session.add(entry)
            session.commit()
        else:
            log.info("OONIProbeServerState already initialized!")
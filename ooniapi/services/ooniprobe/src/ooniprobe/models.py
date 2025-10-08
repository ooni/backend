from datetime import datetime
from .common.models import UtcDateTime
from .common.postgresql import Base
from sqlalchemy import ForeignKey, Sequence, String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column, relationship


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
    generation
    """
    __tablename__ = "ooniprobe_server_state"

    id: Mapped[str] = mapped_column(
        String,
        Sequence("ooniprobe_server_state_id_seq", start=1),
        primary_key=True,
        nullable=False
    )
    date_created: Mapped[datetime] = mapped_column(UtcDateTime())
    secret_key: Mapped[str] = mapped_column()
    public_parameters: Mapped[str] = mapped_column()
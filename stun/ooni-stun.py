#!/usr/bin/env python3

"""
OONI-specific STUN server. Implements a subset of STUN.
Based on https://github.com/martin-steghoefer/fakestun
Released under GPLv3
"""

import ipaddress
import logging
import socket
import time

from setproctitle import setproctitle  # debdeps: python3-setproctitle
from systemd.journal import JournalHandler  # debdeps: python3-systemd
import statsd  # debdeps: python3-statsd


# IP address and UDP port to use for incoming requests
LISTEN_IPADDR = "0.0.0.0"  # Required
LISTEN_PORT = 3478  # Required; normally 3478


# CHANGED-ADDRESS attribute of response
RESPONSE_CHANGED_IPADDR = ""  # If empty return no attribute CHANGED-ADDRESS
RESPONSE_CHANGED_PORT = -1  # If negative return no attribute CHANGED-ADDRESS


log = logging.getLogger("ooni-stun")
log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="ooni-stun"))
log.setLevel(logging.DEBUG)
metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="ooni-stun")

rtt_lookup = {}


def uint16_to_bytes(number):
    return number.to_bytes(2, byteorder="big", signed=False)


class Attribute:
    """STUN response attribute"""

    def __init__(self, attributeType: int) -> None:
        self.__attributeType = attributeType

    def gen_bytes(self):
        attributeValue = self.serialize()
        return (
            uint16_to_bytes(self.__attributeType)
            + uint16_to_bytes(len(attributeValue))
            + attributeValue
        )


class IPv4Attr(Attribute):
    """STUN response attribute consisting of IPv4 address and Port (e.g. for MAPPED-ADDRESS)"""

    MAPPED_ADDR = 1
    SOURCE_ADDR = 4
    CHANGED_ADDR = 5

    def __init__(self, attributeType: int, ipaddr, port: int) -> None:
        super().__init__(attributeType)
        self.__ipaddr = ipaddr
        self.__port = port

    def serialize(self):
        protocolIPv4 = uint16_to_bytes(1)
        port = uint16_to_bytes(self.__port)
        ipaddr = self.__ipaddr
        return protocolIPv4 + port + ipaddr


class TextAttribute(Attribute):
    TYPE_SERVER = 32802

    def __init__(self, attributeType, text):
        super().__init__(attributeType)
        self.__text = text

    def serialize(self):
        return self.__text.encode("utf-8") + b"\x00"


class ResponseMessage:
    """Complete information for a STUN response message"""

    """Message type corresponding to the response to a Binding Request"""

    BINDING_RESPONSE = 257

    def __init__(self, messageType, transaction_id):
        self.__messageType = messageType
        self.__messageTransactionID = transaction_id
        self.__attributes = []

    def add_attribute(self, attribute: Attribute):
        self.__attributes.append(attribute)

    def gen_bytes(self):
        attributesBinary = b"".join(
            map(lambda attribute: attribute.gen_bytes(), self.__attributes)
        )
        return (
            uint16_to_bytes(self.__messageType)
            + uint16_to_bytes(len(attributesBinary))
            + self.__messageTransactionID
            + attributesBinary
        )


def pack_ipaddr(ipaddr: str) -> bytes:
    return ipaddress.IPv4Address(ipaddr).packed


def log_rtt(transaction_id, sock_addr) -> None:
    # Maintains the rtt_lookup dict
    if transaction_id not in rtt_lookup:
        rtt_lookup[transaction_id] = time.perf_counter_ns()

    else:
        t0 = rtt_lookup.pop(transaction_id)
        elapsed = time.perf_counter_ns() - t0


@metrics.timer("handle_request")
def reply(req: bytes, req_ipaddr, req_port: int, sock) -> None:
    log.debug("Received request")
    if len(req) < 21 or req[0:2] != uint16_to_bytes(1):
        log.debug("Unsupported request")
        return

    transaction_id = req[4:20]
    sock_addr_ipa = ipaddress.IPv4Address(req_ipaddr)

    # log_rtt(transaction_id, sock_addr_ipa)

    resp = ResponseMessage(ResponseMessage.BINDING_RESPONSE, transaction_id)

    # MAPPED-ADDRESS attribute
    # (client or NAT ip address)
    mapped_ipaddr = sock_addr_ipa.packed
    resp.add_attribute(IPv4Attr(IPv4Attr.MAPPED_ADDR, mapped_ipaddr, req_port))

    # SOURCE-ADDRESS attribute
    src_ipaddr = ipaddress.IPv4Address(LISTEN_IPADDR).packed
    resp.add_attribute(IPv4Attr(IPv4Attr.SOURCE_ADDR, src_ipaddr, LISTEN_PORT))

    # custom SOURCE-ADDRESS attribute
    # resp.add_attribute(IPv4Attr(IPv4Attr.SOURCE_ADDR, src_ipaddr, src_port))

    # CHANGED-ADDRESS attribute
    # resp.add_attribute(IPv4Attr(IPv4Attr.CHANGED_ADDR, changed_ipaddr,
    # changed_port))

    # SERVER attribute
    # resp.add_attribute(TextAttribute(TextAttribute.TYPE_SERVER, "replaceme"))

    payload = resp.gen_bytes()
    sock.sendto(payload, (req_ipaddr, req_port))


def run():
    setproctitle("ooni-stun")
    log.info("Starting")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IPADDR, LISTEN_PORT))
    log.info("Started")
    while True:
        req, tup = sock.recvfrom(1024)
        req_ipaddr, req_port = tup
        reply(req, req_ipaddr, req_port, sock)


if __name__ == "__main__":
    run()

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

import statsd  # debdeps: python3-statsd
from setproctitle import setproctitle  # debdeps: python3-setproctitle


# IP address and UDP port to use for incoming requests
LISTEN_IPADDR = "0.0.0.0"  # Required
LISTEN_PORT = 3478  # Required; normally 3478


# CHANGED-ADDRESS attribute of response
RESPONSE_CHANGED_IPADDR = ""  # If empty return no attribute CHANGED-ADDRESS
RESPONSE_CHANGED_PORT = -1  # If negative return no attribute CHANGED-ADDRESS


log = logging.getLogger("ooni-stun")
metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="ooni-stun")

rtt_lookup = {}


def uint16_to_bytes(number):
    return number.to_bytes(2, byteorder="big", signed=False)


class Attribute:
    """STUN response attribute"""

    def __init__(self, attributeType):
        self.__attributeType = attributeType

    def gen_bytes(self):
        attributeValue = self.getAttributeValue()
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

    def __init__(self, attributeType, ipaddr, port):
        super().__init__(attributeType)
        self.__ipaddr = ipaddr
        self.__port = port

    def getAttributeValue(self):
        protocolIPv4 = uint16_to_bytes(1)
        port = uint16_to_bytes(self.__port)
        ipaddr = self.__ipaddr
        return protocolIPv4 + port + ipaddr


class TextAttribute(Attribute):
    TYPE_SERVER = 32802

    def __init__(self, attributeType, text):
        super().__init__(attributeType)
        self.__text = text

    def getAttributeValue(self):
        return self.__text.encode("utf-8") + b"\x00"


class ResponseMessage:
    """Complete information for a STUN response message"""

    """Message type corresponding to the response to a Binding Request"""

    BINDING_RESPONSE = 257

    def __init__(self, messageType, transaction_id):
        self.__messageType = messageType
        self.__messageTransactionID = transaction_id
        self.__attributes = []

    def add_attribute(self, attribute):
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


def pick(ipaddr: str, port: int, default_ipaddr, defaultPort: int):
    bothConfigured = True
    if ipaddr:
        p_ipaddr = ipaddress.IPv4Address(ipaddr).packed
    else:
        p_ipaddr = default_ipaddr
        bothConfigured = False
    if port < 0:
        port = defaultPort
        bothConfigured = False
    return (p_ipaddr, port, bothConfigured)


def log_rtt(transaction_id, sock_addr) -> None:
    # Maintains the rtt_lookup dict
    if transaction_id not in rtt_lookup:
        rtt_lookup[transaction_id] = time.perf_counter_ns()

    else:
        t0 = rtt_lookup.pop(transaction_id)
        elapsed = time.perf_counter_ns() - t0


@metrics.timer("handle_request")
def reply(data, addr, sock) -> None:
    log.debug("Received request")
    if data[0:2] != uint16_to_bytes(1):
        log.debug("Unsupported request")
        return

    transaction_id = data[4:20]
    sock_addr = ipaddress.IPv4Address(addr[0])

    # log_rtt(transaction_id, sock_addr)

    resp = ResponseMessage(ResponseMessage.BINDING_RESPONSE, transaction_id)

    # MAPPED-ADDRESS attribute
    mappedIp, mappedPort, _ = pick("", -1, sock_addr.packed, addr[1])
    resp.add_attribute(IPv4Attr(IPv4Attr.MAPPED_ADDR, mappedIp, mappedPort))

    # SOURCE-ADDRESS attribute
    lipa = ipaddress.IPv4Address(LISTEN_IPADDR).packed
    src_ipaddr, src_port, _ = pick("", -1, lipa, LISTEN_PORT)
    resp.add_attribute(IPv4Attr(IPv4Attr.SOURCE_ADDR, src_ipaddr, src_port))

    # custom SOURCE-ADDRESS attribute
    # src_ipaddr, src_port, _ = pick("1.2.3.4", -1, lipa, LISTEN_PORT)
    # resp.add_attribute(IPv4Attr(IPv4Attr.SOURCE_ADDR, src_ipaddr, src_port))

    # CHANGED-ADDRESS attribute
    changed_ipaddr, changed_port, changed = pick(
        RESPONSE_CHANGED_IPADDR, RESPONSE_CHANGED_PORT, None, 0
    )
    if changed:
        resp.add_attribute(
            IPv4Attr(IPv4Attr.CHANGED_ADDR, changed_ipaddr, changed_port)
        )

    # SERVER attribute
    # fixed len?
    # resp.add_attribute(TextAttribute(TextAttribute.TYPE_SERVER, "replaceme"))

    sock.sendto(resp.gen_bytes(), addr)


def run():
    setproctitle("ooni-stun")
    log.info("Starting")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IPADDR, LISTEN_PORT))
    log.info("Started")
    while True:
        req, req_addr = sock.recvfrom(1024)
        reply(req, req_addr, sock)


if __name__ == "__main__":
    run()

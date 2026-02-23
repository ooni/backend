from oonihelpers.common.dependencies import get_settings
from twisted.application import internet, service
from twisted.scripts import twistd
from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker
from oonihelpers.tcp_helpers import Daphn3Server, TCPEchoHelper
from zope.interface import implementer
import sys

import logging
log = logging.getLogger(__name__)

class Options(usage.Options):
    optParameters = []

@implementer(IServiceMaker, IPlugin)
class OONIHelpers(object):
    tapname = "oonihelpers"
    description = "OONI Test Helpers"
    options = Options
    def makeService(self, options):
        settings = get_settings()
        ooniHelpersService = service.MultiService()
        
        # Start the OONI daphn3 backend
        if settings.daphn3_port:
            log.info(f"Starting Daphn3 helper on {settings.daphn3_port}")
            daphn3_helper = internet.TCPServer(settings.daphn3_port, Daphn3Server())
            ooniHelpersService.addService(daphn3_helper)

        # Start the TCP Echo Service
        if settings.tcp_echo_port:
            log.info(f"Starting TCP echo helper on {settings.tcp_echo_port}")
            tcp_echo_helper = internet.TCPServer(settings.tcp_echo_port, TCPEchoHelper())
            ooniHelpersService.addService(tcp_echo_helper)

        return ooniHelpersService

serviceMaker = OONIHelpers()

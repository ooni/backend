"""
In here we define a runner for the oonib backend system.
"""

from __future__ import print_function

from distutils.version import LooseVersion
import tempfile
import os

from shutil import rmtree

from twisted.internet import reactor, endpoints
from twisted.python.runtime import platformType

from txtorcon import TCPHiddenServiceEndpoint, TorConfig
from txtorcon import launch_tor

from oonib.api import ooniBackend, ooniBouncer
from oonib.config import config

from oonib import oonibackend
from oonib import log

from txtorcon import __version__ as txtorcon_version
if tuple(map(int, txtorcon_version.split('.'))) < (0, 9, 0):
    """
    Fix for bug in txtorcon versions < 0.9.0 where TCPHiddenServiceEndpoint
    listens on all interfaces by default.
    """
    def create_listener(self, proto):
        self._update_onion(self.hiddenservice.dir)
        self.tcp_endpoint = endpoints.TCP4ServerEndpoint(self.reactor,
                                                         self.listen_port,
                                                         interface='127.0.0.1')
        d = self.tcp_endpoint.listen(self.protocolfactory)
        d.addCallback(self._add_attributes).addErrback(self._retry_local_port)
        return d
    TCPHiddenServiceEndpoint._create_listener =  create_listener

class OBaseRunner(object):
    pass

if platformType == "win32":
    from twisted.scripts._twistw import WindowsApplicationRunner

    OBaseRunner = WindowsApplicationRunner
    # XXX Currently we don't support windows for starting a Tor Hidden Service
    log.warn(
        "Apologies! We don't support starting a Tor Hidden Service on Windows.")

else:
    from twisted.scripts._twistd_unix import UnixApplicationRunner
    class OBaseRunner(UnixApplicationRunner):
        temporary_data_dir = None

        def txSetupFailed(self, failure):
            log.err("Setup failed")
            log.exception(failure)

        def setupHSEndpoint(self, tor_process_protocol, torconfig, endpoint):
            endpointName = endpoint.settings['name']

            def setup_complete(port):
                if LooseVersion(txtorcon_version) >= LooseVersion('0.10.0'):
                    onion_uri = port.address.onion_uri
                else:
                    onion_uri = port.onion_uri
                print("Exposed %s Tor hidden service "
                      "on httpo://%s" % (endpointName, onion_uri))

            public_port = 80
            data_dir = os.path.join(torconfig.DataDirectory, endpointName)
            if LooseVersion(txtorcon_version) >= LooseVersion('0.10.0'):
                hs_endpoint = TCPHiddenServiceEndpoint(reactor,
                                                       torconfig,
                                                       public_port,
                                                       hidden_service_dir=data_dir)
            else:
                hs_endpoint = TCPHiddenServiceEndpoint(reactor,
                                                       torconfig,
                                                       public_port,
                                                       data_dir=data_dir)
            d = hs_endpoint.listen(endpoint)
            d.addCallback(setup_complete)
            d.addErrback(self.txSetupFailed)
            return d

        def startTor(self, torconfig):
            def updates(prog, tag, summary):
                print("%d%%: %s" % (prog, summary))

            torconfig.SocksPort = config.main.socks_port
            if config.main.tor2webmode:
                torconfig.Tor2webMode = 1
                torconfig.CircuitBuildTimeout = 60
            if config.main.tor_datadir is None:
                self.temporary_data_dir = tempfile.mkdtemp()
                log.warn("Option 'tor_datadir' in oonib.conf is unspecified!")
                log.warn("Using %s" % self.temporary_data_dir)
                torconfig.DataDirectory = self.temporary_data_dir
            else:
                torconfig.DataDirectory = config.main.tor_datadir
            torconfig.save()
            if config.main.tor_binary is not None:
                d = launch_tor(torconfig, reactor,
                               tor_binary=config.main.tor_binary,
                               progress_updates=updates)
            else:
                d = launch_tor(torconfig, reactor, progress_updates=updates)
            return d

        def postApplication(self):
            """After the application is created, start the application and run
            the reactor. After the reactor stops, clean up PID files and such.
            """
            self.startApplication(self.application)
            # This is our addition. The rest is taken from
            # twisted/scripts/_twistd_unix.py 12.2.0
            if config.main.tor_hidden_service:
                torconfig = TorConfig()
                d = self.startTor(torconfig)
                d.addCallback(self.setupHSEndpoint, torconfig, ooniBackend)
                if ooniBouncer:
                    d.addCallback(self.setupHSEndpoint, torconfig, ooniBouncer)
            else:
                if ooniBouncer:
                    reactor.listenTCP(8888, ooniBouncer, interface="127.0.0.1")
                reactor.listenTCP(8889, ooniBackend, interface="127.0.0.1")
            self.startReactor(None, self.oldstdout, self.oldstderr)
            self.removePID(self.config['pidfile'])
            if self.temporary_data_dir:
                log.msg("Removing temporary directory: %s"
                        % self.temporary_data_dir)
                rmtree(self.temporary_data_dir, onerror=log.err)

        def createOrGetApplication(self):
            return oonibackend.application

OBaseRunner.loggerFactory = log.LoggerFactory

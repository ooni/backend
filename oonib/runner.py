# -*- encoding: utf-8 -*-
#
# :authors: Arturo Filastò, Isis Lovecruft
# :licence: see LICENSE for details
"""
In here we define a runner for the oonib backend system.
"""

from __future__ import print_function

import tempfile
import os

from shutil import rmtree

from twisted.internet import reactor
from twisted.application import service, internet, app
from twisted.python.runtime import platformType

from txtorcon import TCPHiddenServiceEndpoint, TorConfig
from txtorcon import launch_tor

from oonib.report.api import reportAPI 
from oonib.api import ooniBackend, ooniBouncer

from oonib import oonibackend
from oonib import config
from oonib import log


class OBaseRunner(object):
    pass

_repo_dir = os.path.join(os.getcwd().split('ooni-backend')[0], 'ooni-backend')

def txSetupFailed(failure):
    log.err("Setup failed")
    log.exception(failure)

def setupHSEndpoint(tor_process_protocol, torconfig, endpoint):
    endpointName = endpoint.settings['name']
    def setup_complete(port):
        print("Exposed %s Tor hidden service on httpo://%s" % (endpointName,
            port.onion_uri))

    public_port = 80
    hs_endpoint = TCPHiddenServiceEndpoint(reactor, torconfig, public_port,
            data_dir=os.path.join(torconfig.DataDirectory, endpointName))
    d = hs_endpoint.listen(endpoint)
    d.addCallback(setup_complete)
    d.addErrback(txSetupFailed)
    return d

def startTor(torconfig):
    def updates(prog, tag, summary):
        print("%d%%: %s" % (prog, summary))

    tempfile.tempdir = os.path.join(_repo_dir, 'tmp')
    if not os.path.isdir(tempfile.gettempdir()):
        os.makedirs(tempfile.gettempdir())
    _temp_dir = tempfile.mkdtemp()

    torconfig.SocksPort = config.main.socks_port
    if config.main.tor2webmode:
        torconfig.Tor2webMode = 1
        torconfig.CircuitBuildTimeout = 60
    if config.main.tor_datadir is None:
        log.warn("Option 'tor_datadir' in oonib.conf is unspecified!")
        log.msg("Creating tmp directory in current directory for datadir.")
        log.debug("Using %s" % _temp_dir)
        datadir = _temp_dir
    else:
        datadir = config.main.tor_datadir
    torconfig.DataDirectory = datadir
    torconfig.save()
    if config.main.tor_binary is not None:
        d = launch_tor(torconfig, reactor,
                       tor_binary=config.main.tor_binary,
                       progress_updates=updates)
    else:
        d = launch_tor(torconfig, reactor, progress_updates=updates)
    return d

if platformType == "win32":
    from twisted.scripts._twistw import WindowsApplicationRunner

    OBaseRunner = WindowsApplicationRunner
    # XXX Currently we don't support windows for starting a Tor Hidden Service
    log.warn(
        "Apologies! We don't support starting a Tor Hidden Service on Windows.")

else:
    from twisted.scripts._twistd_unix import UnixApplicationRunner
    class OBaseRunner(UnixApplicationRunner):
        def postApplication(self):
            """After the application is created, start the application and run
            the reactor. After the reactor stops, clean up PID files and such.
            """
            self.startApplication(self.application)
            # This is our addition. The rest is taken from
            # twisted/scripts/_twistd_unix.py 12.2.0
            if config.main.tor_hidden_service:
                torconfig = TorConfig()
                d = startTor(torconfig)
                d.addCallback(setupHSEndpoint, torconfig, ooniBackend)
                if ooniBouncer:
                    d.addCallback(setupHSEndpoint, torconfig, ooniBouncer)
            else:
                if ooniBouncer:
                    reactor.listenTCP(8888, ooniBouncer, interface="127.0.0.1")
                reactor.listenTCP(8889, ooniBackend, interface="127.0.0.1")
            self.startReactor(None, self.oldstdout, self.oldstderr)
            self.removePID(self.config['pidfile'])
            if os.path.exists(tempfile.gettempdir()):
                log.msg("Removing temporary directory: %s"
                        % tempfile.gettempdir())
                rmtree(tempfile.gettempdir(), onerror=log.err)

        def createOrGetApplication(self):
            return oonibackend.application

OBaseRunner.loggerFactory = log.LoggerFactory

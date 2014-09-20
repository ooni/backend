import tempfile
from oonib import log
from oonib.config import config
from twisted.internet import reactor, endpoints
import os

from random import randint
import socket

from txtorcon import TCPHiddenServiceEndpoint, TorConfig
from txtorcon import launch_tor

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

def randomFreePort(addr="127.0.0.1"):
    """
    Args:

        addr (str): the IP address to attempt to bind to.

    Returns an int representing the free port number at the moment of calling

    Note: there is no guarantee that some other application will attempt to
    bind to this port once this function has been called.
    """
    free = False
    while not free:
        port = randint(1024, 65535)
        s = socket.socket()
        try:
            s.bind((addr, port))
            free = True
        except:
            pass
        s.close()
    return port

def txSetupFailed(failure):
    log.err("Setup failed")
    log.exception(failure)

def startTor(torconfig):
    def updates(prog, tag, summary):
        print("%d%%: %s" % (prog, summary))

    if config.main.socks_port:
        torconfig.SocksPort = config.main.socks_port
    if config.main.control_port:
        torconfig.ControlPort = config.main.control_port
    if config.main.tor2webmode:
        torconfig.Tor2webMode = 1
        torconfig.CircuitBuildTimeout = 60
    if config.main.tor_datadir is None:
        temporary_data_dir = tempfile.mkdtemp()
        log.warn("Option 'tor_datadir' in oonib.conf is unspecified!")
        log.warn("Using %s" % temporary_data_dir)
        torconfig.DataDirectory = temporary_data_dir
    else:
        if os.path.exists(config.main.tor_datadir):
            torconfig.DataDirectory = os.path.abspath(config.main.tor_datadir)
        else:
            raise Exception

    tor_log_file = os.path.join(torconfig.DataDirectory, "tor.log")
    torconfig.Log = ["notice stdout", "notice file %s" % tor_log_file]
    torconfig.save()
    if not hasattr(torconfig, 'ControlPort'):
        control_port = int(randomFreePort())
        torconfig.ControlPort = control_port
        config.main.control_port = control_port

    if not hasattr(torconfig, 'SocksPort'):
        socks_port = int(randomFreePort())
        torconfig.SocksPort = socks_port
        config.main.socks_port = socks_port

    torconfig.save()

    if config.main.tor_binary is not None:
        d = launch_tor(torconfig, reactor,
                       tor_binary=config.main.tor_binary,
                       progress_updates=updates)
    else:
        d = launch_tor(torconfig, reactor, progress_updates=updates)
    return d

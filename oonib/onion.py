import pwd
import tempfile

from oonib import log
from oonib.config import config
from twisted.internet import defer
import os

from random import randint
import socket

from txtorcon import TorConfig
from txtorcon import launch_tor

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

def _configTor():
    torconfig = TorConfig()

    if config.main.socks_port is None:
        config.main.socks_port = int(randomFreePort())
    torconfig.SocksPort = config.main.socks_port

    if config.main.control_port is None:
        config.main.control_port = int(randomFreePort())
    torconfig.ControlPort = config.main.control_port

    if config.main.tor2webmode is True:
        torconfig.Tor2webMode = 1
        torconfig.CircuitBuildTimeout = 60
    if config.main.tor_datadir is None:
        temporary_data_dir = tempfile.mkdtemp()
        log.warn("Option 'tor_datadir' in oonib.conf is unspecified!")
        log.warn("Using %s" % temporary_data_dir)
        torconfig.DataDirectory = temporary_data_dir
        uid = -1
        gid = -1
        if config.main.uid is not None:
            uid = config.main.uid
        if config.main.gid is not None:
            gid = config.main.gid
        os.chown(temporary_data_dir, uid, gid)
    else:
        if os.path.exists(config.main.tor_datadir):
            torconfig.DataDirectory = os.path.abspath(config.main.tor_datadir)
        else:
            raise Exception("Could not find tor datadir")

    if config.main.uid is not None:
        try:
            user = pwd.getpwuid(config.main.uid)[0]
        except KeyError:
            raise Exception("Invalid user ID")
        torconfig.User = user

    tor_log_file = os.path.join(torconfig.DataDirectory, "tor.log")
    torconfig.Log = ["notice stdout", "notice file %s" % tor_log_file]
    torconfig.save()
    return torconfig

# get_global_tor is a near-rip of that from txtorcon (so you can have some
# confidence in the logic of it), but we use our own _configTor() while
# the txtorcon function hardcodes some default values we don't want.
_global_tor_config = None
_global_tor_lock = defer.DeferredLock()
# we need the lock because we (potentially) yield several times while
# "creating" the TorConfig instance

@defer.inlineCallbacks
def get_global_tor(reactor):
    global _global_tor_config
    global _global_tor_lock
    yield _global_tor_lock.acquire()

    try:
        if _global_tor_config is None:
            _global_tor_config = _configTor()

            # start Tor launching
            def updates(prog, tag, summary):
                log.msg("%d%%: %s" % (prog, summary))
            yield launch_tor(_global_tor_config, reactor,
                    progress_updates=updates,
                    tor_binary=config.main.tor_binary)
            yield _global_tor_config.post_bootstrap

        defer.returnValue(_global_tor_config)
    finally:
        _global_tor_lock.release()

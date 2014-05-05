# -*- encoding: utf-8 -*-
#
# :authors: Arturo Filastò, Isis Lovecruft
# :licence: see LICENSE for details
"""
Twisted logger for the ooni backend system.
"""

import os
import sys
import codecs
import logging
import traceback

from twisted.python import log as txlog
from twisted.python import util
from twisted.python.failure import Failure
from twisted.python.logfile import DailyLogFile

from oonib import otime
from oonib.config import config

# Get rid of the annoying "No route found for
# IPv6 destination warnings":
logging.getLogger("scapy.runtime").setLevel(logging.ERROR)


def log_encode(logmsg):
    """
    I encode logmsg (a str or unicode) as printable ASCII. Each case
    gets a distinct prefix, so that people differentiate a unicode
    from a utf-8-encoded-byte-string or binary gunk that would
    otherwise result in the same final output.
    """
    if isinstance(logmsg, unicode):
        return codecs.encode(logmsg, 'unicode_escape')
    elif isinstance(logmsg, str):
        try:
            unicodelogmsg = logmsg.decode('utf-8')
        except UnicodeDecodeError:
            return codecs.encode(logmsg, 'string_escape')
        else:
            return codecs.encode(unicodelogmsg, 'unicode_escape')
    else:
        raise Exception("I accept only a unicode object or a string, "
                        "not a %s object like %r" % (type(logmsg),
                                                     repr(logmsg)))


class LogWithNoPrefix(txlog.FileLogObserver):
    def emit(self, eventDict):
        text = txlog.textFromEventDict(eventDict)
        if text is None:
            return

        util.untilConcludes(self.write, "%s\n" % text)
        util.untilConcludes(self.flush)  # Hoorj!


def start(application_name="oonib"):
    daily_logfile = None

    if not config.main.logfile:
        logfile = 'oonib.log'
    else:
        logfile = config.main.logfile

    log_folder = os.path.dirname(logfile)
    log_filename = os.path.basename(logfile)

    daily_logfile = DailyLogFile(log_filename, log_folder)

    txlog.msg("Starting %s on %s (%s UTC)" % (application_name,
                                              otime.prettyDateNow(),
                                              otime.utcPrettyDateNow()))
    txlog.msg("oonib version %s" % config.backend_version)
    txlog.startLoggingWithObserver(LogWithNoPrefix(sys.stdout).emit)
    txlog.addObserver(txlog.FileLogObserver(daily_logfile).emit)


def stop():
    print "Stopping OONI"


def msg(msg, *arg, **kw):
    print "%s" % log_encode(msg)


def debug(msg, *arg, **kw):
    if config.main.get('debug'):
        print "[D] %s" % log_encode(msg)


def warn(msg, *arg, **kw):
    print "[W] %s" % log_encode(msg)


def err(msg, *arg, **kw):
    print "[!] %s" % log_encode(msg)


def exception(error):
    """
    Error can either be an error message to print to stdout and to the logfile
    or it can be a twisted.python.failure.Failure instance.
    """
    if isinstance(error, Failure):
        error.printTraceback()
    else:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback)


class LoggerFactory(object):
    """
    This is a logger factory to be used by oonib
    """
    def __init__(self, options):
        pass

    def start(self, application):
        start("OONIB")

    def stop(self):
        txlog.msg("Stopping OONIB")

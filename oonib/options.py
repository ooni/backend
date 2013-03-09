from twisted.python import usage
from twisted.python.runtime import platformType
from twisted.python import usage

if platformType == "win32":
    from twisted.scripts._twistw import ServerOptions
else:
    from twisted.scripts._twistd_unix import ServerOptions

#class OONIBOptions(usage.Options):
class OONIBOptions(usage.Options):
    synopsis = """%s [options] [path to test].py """

    longdesc = ("oonib provides the backend component of ooni-probe. oonib provides test helper services and a reporting backend service. oonib is intended to be run as a daemon and most options are set in its configuration file")
    
    optParameters = [["config", "c", "oonib.conf", "Path to config file"]]

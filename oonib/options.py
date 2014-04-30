from twisted.python import usage


class OONIBOptions(usage.Options):
    synopsis = """%s [options]"""

    longdesc = ("oonib provides the backend component of ooni-probe."
                "oonib provides test helper services and a reporting "
                "backend service. oonib is intended to be run as a "
                "daemon and most options are set in its configuration file")

    optParameters = [["config", "c", "oonib.conf", "Path to config file"]]

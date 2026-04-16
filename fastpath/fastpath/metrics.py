# -*- coding: utf-8 -*-

"""
Metric generation
"""

from os.path import basename, splitext

import os
import statsd  # debdeps: python3-statsd
import logging


log = logging.getLogger("fastpath")

def setup_metrics(host="localhost", name=None):
    """Setup metric generation. Use dotted namespaces e.g.
    "pipeline.centrifugation"
    """
    statsd_host = os.getenv("STATSD_HOST", host)
    statsd_port = os.getenv("STATSD_PORT", 8125)

    log.debug("got {statsd_host}:{statsd_port} for statsd")
    if name is None:
        import __main__

        prefix = splitext(basename(__main__.__file__))[0]
    else:
        prefix = name

    prefix = prefix.strip(".")
    return statsd.StatsClient(statsd_host, statsd_port, prefix=prefix)

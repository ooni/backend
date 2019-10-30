# -*- coding: utf-8 -*-

"""
Metric generation
"""

from os.path import basename, splitext

import statsd  # debdeps: python3-statsd


def setup_metrics(host="localhost", name=None):
    """Setup metric generation. Use dotted namespaces e.g.
    "pipeline.centrifugation"
    """
    if name is None:
        import __main__

        prefix = splitext(basename(__main__.__file__))[0]
    else:
        prefix = name

    prefix = prefix.strip(".")
    return statsd.StatsClient(host, 8125, prefix=prefix)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Receive measurements by listening on localhost
"""
import os
from queue import Full

from gunicorn.app.base import BaseApplication


API_PORT = int(os.environ.get("FASTPATH_API_PORT", 8472))
# QUEUE_PUT_TIMEOUT set to -1 means that we block
QUEUE_PUT_TIMEOUT = int(os.environ.get("FASTPATH_QUEUE_PUT_TIMEOUT", -1))
if QUEUE_PUT_TIMEOUT == -1:
    QUEUE_PUT_TIMEOUT = None
WORKER_TIMEOUT = int(os.environ.get("FASTPATH_WORKER_TIMEOUT", 30))

class MsmtFeeder(BaseApplication):
    def __init__(self, app, conf):
        self._conf = conf
        self.application = app
        super().__init__()

    def load_config(self):
        for key, value in self._conf.items():
            assert key in self.cfg.settings
            self.cfg.set(key, value)

    def load(self):
        return self.application


def make_handler_app(queue, accepting):
    """WSGI app that puts POSTed measurements in the queue.
    Answers 503 when the measurement processors are gone (accepting is
    cleared) or the queue stays full, so that the API tries another
    fastpath instead of losing the measurement.
    """

    def handler_app(environ, start_response):
        if environ["REQUEST_METHOD"] == "POST":
            if not accepting.is_set():
                start_response("503 Service Unavailable", [])
                return [b""]
            # TODO:pass msmt_uid
            path = environ["PATH_INFO"]
            assert path.startswith("/2")
            msmt_uid = path[1:]
            data = environ["wsgi.input"].read()
            msm_tup = (data, None, msmt_uid)
            try:
                queue.put(msm_tup, block=True, timeout=QUEUE_PUT_TIMEOUT)
            except Full:
                start_response("503 Service Unavailable", [])
                return [b""]

        start_response("200 OK", [])
        return [b""]

    return handler_app


def start_http_api(queue, accepting):
    options = {
        "bind": f"0.0.0.0:{API_PORT}",
        "timeout": WORKER_TIMEOUT,
        "control_socket_disable": True,
    }
    print(f"starting localhttpfeeder with worker_timeout: {WORKER_TIMEOUT} and"
          f" queue_put_timeout: {QUEUE_PUT_TIMEOUT}", flush=True)

    MsmtFeeder(make_handler_app(queue, accepting), options).run()

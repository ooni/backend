#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Receive measurements by listening on localhost
"""
import os
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


def start_http_api(queue):

    def handler_app(environ, start_response):
        if environ["REQUEST_METHOD"] == "POST":
            # TODO:pass msmt_uid
            path = environ["PATH_INFO"]
            assert path.startswith("/2")
            msmt_uid = path[1:]
            data = environ["wsgi.input"].read()
            msm_tup = (data, None, msmt_uid)
            queue.put(msm_tup, block=True, timeout=QUEUE_PUT_TIMEOUT)

        start_response("200 OK", [])
        return [b""]

    options = {
        "bind": f"0.0.0.0:{API_PORT}",
        "timeout": WORKER_TIMEOUT,
    }
    print(f"starting localhttpfeeder with worker_timeout: {WORKER_TIMEOUT} and"
          " queue_put_timeout: {QUEUE_PUT_TIMEOUT}")
    MsmtFeeder(handler_app, options).run()

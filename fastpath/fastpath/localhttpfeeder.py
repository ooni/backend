#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Receive measurements by listening on localhost
"""

from gunicorn.app.base import BaseApplication
from logging import getLogger

log = getLogger(__file__)

API_PORT = 8472


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
            try:
                log.debug(f"Read measurement uid: {msmt_uid}")
                data = environ["wsgi.input"].read()
                msm_tup = (data, None, msmt_uid)
                queue.put(msm_tup, block=False, timeout=10)
            except Exception as e:
                log.error(f"Error trying to read request {msmt_uid}: {e}")

        start_response("200 OK", [])
        return [b""]

    options = {"bind": f"0.0.0.0:{API_PORT}"}
    MsmtFeeder(handler_app, options).run()

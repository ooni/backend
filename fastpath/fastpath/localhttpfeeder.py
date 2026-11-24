#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Receive measurements by listening on localhost
"""
import os
from queue import Full

from gunicorn.app.base import BaseApplication

from fastpath.metrics import setup_metrics


API_PORT = int(os.environ.get("FASTPATH_API_PORT", 8472))
# Seconds to wait for room in the queue before answering 503. Set to -1 to
# block until there is room.
QUEUE_PUT_TIMEOUT = int(os.environ.get("FASTPATH_QUEUE_PUT_TIMEOUT", -1))
if QUEUE_PUT_TIMEOUT == -1:
    QUEUE_PUT_TIMEOUT = None
WORKER_TIMEOUT = int(os.environ.get("FASTPATH_WORKER_TIMEOUT", 30))

metrics = setup_metrics(name="fastpath")

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


def make_handler_app(queue):
    """WSGI app that puts POSTed measurements in the queue.
    Answers 503 when the queue is still full after QUEUE_PUT_TIMEOUT, so the
    API sends the measurement to another fastpath or to S3 instead of
    waiting on this one.
    """

    def handler_app(environ, start_response):
        if environ["REQUEST_METHOD"] == "POST":
            # TODO:pass msmt_uid
            path = environ["PATH_INFO"]
            assert path.startswith("/2")
            msmt_uid = path[1:]
            data = environ["wsgi.input"].read()
            msm_tup = (data, None, msmt_uid)
            try:
                queue.put(msm_tup, block=True, timeout=QUEUE_PUT_TIMEOUT)
            except Full:
                metrics.incr("queue_full")
                start_response("503 Service Unavailable", [])
                return [b""]

        start_response("200 OK", [])
        return [b""]

    return handler_app


def start_http_api(queue):
    def flush_queue(server, worker):
        # Measurements this HTTP worker has queued may still sit in the queue's
        # buffer in this process. Write them to the pipe before the worker exits,
        # or they are lost.
        queue.close()
        queue.join_thread()

    options = {
        "bind": f"0.0.0.0:{API_PORT}",
        "timeout": WORKER_TIMEOUT,
        "control_socket_disable": True,
        "worker_exit": flush_queue,
    }
    print(f"starting localhttpfeeder with worker_timeout: {WORKER_TIMEOUT} and"
          f" queue_put_timeout: {QUEUE_PUT_TIMEOUT}", flush=True)

    MsmtFeeder(make_handler_app(queue), options).run()

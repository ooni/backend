import sys
import os
import json
import time
import socket
import shutil

from twisted.python.filepath import FilePath
from twisted.internet import reactor, defer
from twisted.trial import unittest

from oonib.config import config

from cyclone import httpclient


def random_unused_port(bind_address='127.0.0.1'):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def mock_initialize(self):
    self.report_dir = FilePath('.')
    self.archive_dir = FilePath('.')
    self.policy_file = None
    self.helpers = {}
    self.stale_time = 10


class HandlerTestCase(unittest.TestCase):
    app = None
    _port = None
    _listener = None
    config_filename = ''

    @property
    def port(self):
        if not self._port:
            self._port = random_unused_port()
        return self._port

    def make_dir(self, dir):
        if not os.path.exists(dir):
            os.makedirs(dir)
            try:
                self.directories.add(dir)
            except AttributeError:
                self.directories = set([dir])

    def setUp(self, *args, **kw):
        self.filenames = set()
        if 'directories' not in dir(self):
            self.directories = set()
        self.old_arguments = sys.argv
        if self.config_filename != '':
            sys.argv = ['test_oonib', '-c', self.config_filename]
            config.load()
        if self.app:
            self._listener = reactor.listenTCP(self.port, self.app)
        config.main.report_dir = "."
        config.main.archive_dir = "."
        config.main.stale_time = 100
        return super(HandlerTestCase, self).setUp()

    def tearDown(self):
        sys.argv = self.old_arguments
        for filename in self.filenames:
            if os.path.exists(filename):
                os.remove(filename)
        for dir in self.directories:
            shutil.rmtree(dir)
        if self._listener:
            self._listener.stopListening()

    @defer.inlineCallbacks
    def request(self, path, method="GET", postdata=None, headers={}):
        url = "http://localhost:%s%s" % (self.port, path)
        if isinstance(postdata, dict):
            postdata = json.dumps(postdata)

        response = yield httpclient.fetch(url, method=method,
                                          postdata=postdata,
                                          headers=headers)
        defer.returnValue(response)

class MockTime(object):
    def __init__(self):
        self._offset = 0

    def advance(self, seconds):
        self._offset += seconds

    def time(self):
        return time.time() + self._offset

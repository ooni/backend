"""
/report

/pcap

This is the async pcap reporting system. It requires the client to have created
a report already, but can work independently from test progress.

"""
import random
import string
import json
import re
import os

from twisted.internet import reactor, defer

from cyclone import web

from oonib import otime
from oonib import randomStr

from oonib import config
from oonib.policy import DeckListHandler, InputListHandler, NetTestListHandler

#XXX: if policy is configured
policyAPI = [
    (r"/deck", DeckListHandler),
    (r"/input", InputListHandler),
    (r"/deck/([a-z0-9]{40})$", DeckDescHandler),
    (r"/deck/([a-z0-9]{40})/file$", web.StaticFileHandler, {"path":
        config.main.deck_dir}),
    (r"/input/([a-z0-9]{40})/file$", web.StaticFileHandler, {"path":
        config.main.input_dir}),
    (r"/input([a-z0-9]{40}$", InputDescHandler),
    (r"/policy/nettest", NetTestListHandler),
    (r"/policy/nettest/([a-z0-9]+/py$", web.StaticFileHandler, {"path":
        config.main.nettest_dir}),
    (r"/policy/input", InputListHandler
]

from cyclone import web

from oonib.main.api import mainAPI
from oonib.deck.api import deckAPI
from oonib.report.api import reportAPI
from oonib.input.api import inputAPI
from oonib.policy.api import policyAPI
from oonib.bouncer.api import bouncerAPI

from oonib.config import config

ooniBouncer = None
ooniBackendAPI = []
ooniBackendAPI += reportAPI

if config.main.input_dir:
    ooniBackendAPI += inputAPI

if config.main.deck_dir:
    ooniBackendAPI += deckAPI

if config.main.policy_file:
    ooniBackendAPI += policyAPI

if config.main.bouncer_file:
    ooniBouncer = web.Application(bouncerAPI, debug=True, name='bouncer')

ooniBackendAPI += mainAPI
ooniBackend = web.Application(ooniBackendAPI, debug=True, name='collector')

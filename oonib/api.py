from cyclone import web

from oonib.deck.api import deckAPI
from oonib.report.api import reportAPI
from oonib.input.api import inputAPI
from oonib.policy.api import policyAPI
from oonib.bouncer.api import bouncerAPI

from oonib import config

ooniBackendAPI = []
ooniBackendAPI += reportAPI

if config.main.input_dir:
    ooniBackendAPI += inputAPI

if config.main.deck_dir:
    ooniBackendAPI += deckAPI

if config.main.policy_file:
    ooniBackendAPI += policyAPI

if config.main.bouncer_file:
    ooniBackendAPI += bouncerAPI

print ooniBackendAPI

ooniBackend = web.Application(ooniBackendAPI, debug=True)

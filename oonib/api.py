from cyclone import web

from oonib.deck.api import deckAPI
from oonib.inputs.api import inputsAPI
from oonib.policy.api import policyAPI
from oonib.bouncer.api import bouncerAPI

from oonib import config

class OONIBHandler(web.RequestHandler):
    pass

class OONIBError(web.HTTPError):
    pass

oonibAPI = []
oonibAPI += reportAPI

if config.inputs_dir:
    oonibAPI += inputsAPI

if config.deck_dir:
    oonibAPI += deckAPI

if config.policy_file:
    oonibAPI += policyAPI

if config.bouncer_file:
    oonibAPI += bouncerAPI



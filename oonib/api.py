from oonib.deck.api import deckAPI
from oonib.report.api import reportAPI
from oonib.inputs.api import inputsAPI
from oonib.policy.api import policyAPI
from oonib.bouncer.api import bouncerAPI

from oonib import config

oonibAPI = []
oonibAPI += reportAPI

if config.main.inputs_dir:
    oonibAPI += inputsAPI

if config.main.deck_dir:
    oonibAPI += deckAPI

if config.main.policy_file:
    oonibAPI += policyAPI

if config.main.bouncer_file:
    oonibAPI += bouncerAPI

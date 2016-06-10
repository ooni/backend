from cyclone import web


from oonib.config import config

class OONICollector(web.Application):
    def __init__(self):
        from oonib.main.api import mainAPI
        from oonib.deck.api import deckAPI
        from oonib.report.api import reportAPI
        from oonib.input.api import inputAPI
        from oonib.policy.api import policyAPI
        from oonib.report.handlers import checkForStaleReports

        handlers = []
        handlers += reportAPI

        if config.main.input_dir:
            handlers += inputAPI

        if config.main.deck_dir:
            handlers += deckAPI

        if config.main.policy_file:
            handlers += policyAPI

        handlers += mainAPI

        checkForStaleReports()

        web.Application.__init__(self, handlers, name='collector')


class OONIBouncer(web.Application):
    def __init__(self):
        from oonib.bouncer.api import bouncerAPI

        handlers = []
        handlers += bouncerAPI

        # Follows the same pattern as the above so we can put some
        # initialisation logic for the bouncer as well in here perhaps in
        # the future.
        web.Application.__init__(self, handlers, name='bouncer')

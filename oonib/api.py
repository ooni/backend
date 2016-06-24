from cyclone import web


from oonib import log
from oonib.config import config

class _LaxDict(dict):
    """
    This is like a dictionary, but when a key is missing it returns the
    empty string.
    """
    def __missing__(self, _):
        return ""

def log_function(handler):
    values = _LaxDict({
        'request_time': 1000.0 * handler.request.request_time(),
        'protocol': handler.request.protocol,
        'status': str(handler.get_status()),
        'request_method': handler.request.method,
        'request_uri': handler.request.uri,
        'remote_ip': handler.request.remote_ip
    })
    log_format = config.main.log_format
    if not log_format:
        log_format = ("[{protocol}] {status} {request_method} {request_uri} "
                      "127.0.0.1 {request_time}ms")
    log.msg(log_format.format(**values))


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

        web.Application.__init__(self, handlers, name='collector',
                                 log_function=log_function)


class OONIBouncer(web.Application):
    def __init__(self):
        from oonib.bouncer.api import bouncerAPI

        handlers = []
        handlers += bouncerAPI

        # Follows the same pattern as the above so we can put some
        # initialisation logic for the bouncer as well in here perhaps in
        # the future.
        web.Application.__init__(self, handlers, name='bouncer',
                                 log_function=log_function)

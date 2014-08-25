import types

from cyclone import escape
from cyclone import web

from oonib import log


class OONIBHandler(web.RequestHandler):

    def write_error(self, status_code, exception=None, **kw):
        self.set_status(status_code)
        if hasattr(exception, 'log_message') and exception.log_message is not None:
            self.write({'error': exception.log_message})
        elif 400 <= status_code < 600:
            self.write({'error': status_code})
        else:
            log.exception(exception)
            self.write({'error': 'error'})

    def write(self, chunk):
        """
        This is a monkey patch to RequestHandler to allow us to serialize also
        json list objects.
        """
        if isinstance(chunk, types.ListType):
            chunk = escape.json_encode(chunk)
            web.RequestHandler.write(self, chunk)
            self.set_header("Content-Type", "application/json")
        else:
            web.RequestHandler.write(self, chunk)

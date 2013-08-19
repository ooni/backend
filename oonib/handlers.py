import types

from cyclone import escape
from cyclone import web

class OONIBHandler(web.RequestHandler):
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

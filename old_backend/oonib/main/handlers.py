from oonib.handlers import OONIBHandler


class OONIBGlobalHandler(OONIBHandler):
    """
        Global handler to catch all orphaned requests.
    """
    def default(self):
        # XXX: Waiting to a stable release of cyclone which implements the default handler
        return self.write_error(404)

    def get(self):
        return self.default()

    def post(self):
        return self.default()

    def options(self):
        return self.default()

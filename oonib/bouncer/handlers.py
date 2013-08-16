from oonib.handlers import OONIBHandler

class BouncerQueryHandler(OONIBHandler):
    def get(self):
        #XXX unused
        pass

    def post(self):
        pass
        # request.get?
        #'collector': {'foo.onion': {'helper-name': 'helper-address'}, 'bar.onion': {'helper-name': 'helper-address'}} 

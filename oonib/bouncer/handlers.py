class BouncerQueryHandler(web.RequestHandler):
    def get(self):
        #XXX unused
        pass

    def post(self):
        pass
        # request.get?
        #'collector': {'foo.onion': {'helper-name': 'helper-address'}, 'bar.onion': {'helper-name': 'helper-address'}} 

class CollectorRegisterHandler(self):
    def post(self):
        #XXX: update the list of collectors to query
        pass

    def get(self):
        pass
        #XXX unused


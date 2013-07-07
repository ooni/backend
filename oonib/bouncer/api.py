from oonib.bouncer.handlers import *
#XXX: if bouncer is configured
bouncerAPI = [
        #return a collector and helper of the requested type
        (r"/bouncer", BouncerQueryHandler),
        #XXX: register a collector or helper
        (r"/register", CollectorRegisterHandler),
]

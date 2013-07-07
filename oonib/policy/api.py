from cyclone import web
from oonib.policy import handlers
from oonib import config

#XXX: if policy is configured
policyAPI = [
    (r"/policy/nettest", handlers.NetTestPolicyHandler),
    #XXX: add nettest handler
    #(r"/policy/nettest/([a-z0-9]+)/py$", web.StaticFileHandler, {"path":
    #    config.main.nettest_dir}),
    (r"/policy/input", handlers.InputPolicyHandler),
]

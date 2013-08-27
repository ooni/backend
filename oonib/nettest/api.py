from cyclone import web
from oonib.nettest import handlers
from oonib import config

nettestAPI = [
    (r"/nettest", handlers.NetTestListHandler),
    (r"/nettest/([a-f0-9]{64})", handlers.NetTestDescHandler),
    (r"/nettest/([a-f0-9]{64})/py$", web.StaticFileHandler, {"path":
        config.main.nettest_dir}),
]

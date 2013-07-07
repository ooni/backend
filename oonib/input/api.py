from cyclone import web
from oonib.input import handlers
from oonib import config

inputAPI = [
    (r"/input", handlers.InputListHandler),
    (r"/input/([a-z0-9]{40})", handlers.InputDescHandler),
    (r"/input/([a-z0-9]{40})/file$", web.StaticFileHandler, {"path":
        config.main.input_dir}),
]

from cyclone import web
from oonib.input import handlers
from oonib.config import config

inputAPI = [
    (r"/input", handlers.InputListHandler),
    (r"/input/([a-f0-9]{64})", handlers.InputDescHandler),
    (r"/input/([a-f0-9]{64})/file$", web.StaticFileHandler,
     {"path": config.main.input_dir}),
]

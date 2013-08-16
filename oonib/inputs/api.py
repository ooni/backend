from cyclone import web
from oonib.input import handlers
from oonib import config

inputsAPI = [
    (r"/inputs", handlers.InputsListHandler),
    (r"/inputs/([a-z0-9]{40})", handlers.InputsDescHandler),
    (r"/inputs/([a-z0-9]{40})/file$", web.StaticFileHandler, {"path":
        config.main.inputs_dir}),
]

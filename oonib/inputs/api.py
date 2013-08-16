from cyclone import web
from oonib.inputs import handlers
from oonib import config

inputsAPI = [
    (r"/inputs", handlers.InputsListHandler),
    (r"/inputs/([a-f0-9]{64})", handlers.InputsDescHandler),
    (r"/inputs/([a-f0-9]{64})/file$", web.StaticFileHandler, {"path":
        config.main.inputs_dir}),
]

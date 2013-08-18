from cyclone import web
from oonib.deck import handlers
from oonib import config

deckAPI = [
    (r"/deck", handlers.DeckListHandler),
    (r"/deck/([a-z0-9]{40})$", handlers.DeckDescHandler),
    (r"/deck/([a-z0-9]{40})/yaml$", web.StaticFileHandler, {"path":
        config.main.deck_dir}),
]

from cyclone import web
from oonib.deck import handlers
from oonib.config import config

deckAPI = [
    (r"/deck", handlers.DeckListHandler),
    (r"/deck/([a-z0-9]{64})$", handlers.DeckDescHandler),
    (r"/deck/([a-z0-9]{64})/file$", web.StaticFileHandler,
     {"path": config.main.deck_dir}),
]

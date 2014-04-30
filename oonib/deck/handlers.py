import glob
import os
import re
import yaml

from oonib import errors as e
from oonib.handlers import OONIBHandler
from oonib import log
from oonib.config import config


class DeckDescHandler(OONIBHandler):
    def get(self, deckID):
        # note:
        # we don't have to sanitize deckID, because it's already checked
        # against matching a certain pattern in the handler.
        bn = os.path.basename(deckID + '.desc')
        try:
            f = open(os.path.join(config.main.deck_dir, bn))
        except IOError:
            log.err("Deck %s missing" % deckID)
            raise e.MissingDeck
        with f:
            deckDesc = yaml.safe_load(f)

        response = {}
        for k in ['name', 'description', 'version', 'author', 'date']:
            try:
                response[k] = deckDesc[k]
            except KeyError:
                log.err("Deck %s missing required keys!" % deckID)
                raise e.MissingDeckKeys
        self.write(response)


class DeckListHandler(OONIBHandler):
    def get(self):
        if not config.main.deck_dir:
            self.set_status(501)
            raise e.NoDecksConfigured

        path = os.path.abspath(config.main.deck_dir) + "/*"
        decknames = map(os.path.basename, glob.iglob(path))
        decknames = filter(lambda y: re.match("[a-z0-9]{64}.desc", y),
                           decknames)
        deckList = []
        for deckname in decknames:
            with open(os.path.join(config.main.deck_dir, deckname)) as f:
                d = yaml.safe_load(f)
                deckList.append({
                    'id': deckname,
                    'name': d['name'],
                    'description': d['description']
                })
        self.write(deckList)

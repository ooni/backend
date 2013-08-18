import glob
import json
import os
import re
import yaml

from oonib.handlers import OONIBHandler
from oonib import config, log

class DeckDescHandler(OONIBHandler):
    def get(self, deckID):
        bn = os.path.basename(deckID)
        try:
            f = open(os.path.join(config.main.deck_dir, bn))
            a = {}
            deckDesc = yaml.safe_load(f)
            for k in ['name', 'description', 'version', 'author', 'date']:
                a[k] = deckDesc[k]
            self.write(json.dumps(a))
        except IOError:
            log.err("Deck %s missing" % deckID)
        except KeyError:
            log.err("Deck %s missing required keys!" % deckID)

class DeckListHandler(OONIBHandler):
    def get(self):
        if not config.main.deck_dir: return
        path = os.path.abspath(config.main.deck_dir) + "/*"
        decknames = map(os.path.basename, glob.iglob(path))
        decknames = filter(lambda y: re.match("[a-z0-9]{40}", y), decknames)
        deckList = []
        for deckname in decknames:
            f = open(os.path.join(config.main.deck_dir, deckname))
            d = yaml.safe_load(f)
            deckList.append({'id': deckname,'name': d['name'],
                'description': d['description']})
            f.close()
        self.write(json.dumps(deckList))

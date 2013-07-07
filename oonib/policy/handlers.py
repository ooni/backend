from cyclone import web
from oonib import config
import json
import os
import yaml

class DeckDescHandler(web.RequestHandler):
    def get(self, deckID):
        bn = os.path.basename(deckID)
        try:
            f = open(os.path.join(config.main.deck_dir, bn))
            a = {}
            deckDesc = yaml.safe_load(f)
            a['id'] = deckID
            a['name'] = deckDesc['name']
            a['description'] = deckDesc['description']
            self.write(json.dumps(a))
        except IOError:
            log.err("Deck %s missing" % deckID)
        except KeyError:
            log.err("Deck %s missing required keys!" % deckID)

class DeckListHandler(web.RequestHandler):
    def get(self):
        if not config.main.deck_dir: return
        path = os.path.abspath(config.main.deck_dir) + "/*"
        decknames = map(os.path.basename, glob.iglob(path))
        deckList = []
        for deckname in decknames:
            f = open(os.path.join(config.main.deck_dir, deckname))
            d = yaml.safe_load(f)
            deckList.append({'id': deckname,'name': d['name'],
                'description': d['description']})
            f.close()
        self.write(json.dumps(deckList))

class InputDescHandler(web.RequestHandler):
    def get(self, inputID):
        #XXX return the input descriptor
        # see oonib.md in ooni-spec
        bn = os.path.basename(inputID) + ".desc"
        try:
            f = open(os.path.join(config.main.input_dir, bn))
            a = {}
            inputDesc = yaml.safe_load(f)
            a['id'] = inputID
            a['name'] = inputDesc['name']
            a['description'] = inputDesc['description']
            self.write(json.dumps(a))
        except Exception:
            log.err("No Input Descriptor found for id %s" % inputID) 

class InputListHandler(web.RequestHandler):
    def get(self):
        if not config.main.input_dir: return
        path = os.path.abspath(config.main.input_dir) + "/*"
        inputnames = map(os.path.basename, glob.iglob(path))
        inputList = []
        for inputname in inputnames:
            f = open(os.path.join(config.main.input_dir, deckname))
            d = yaml.safe_load(f)
            inputList.append({'id': inputname,'name': d['name'],
                'description': d['description']})
            f.close()
        self.write(json.dumps(inputList))

class NetTestListHandler(web.RequestHandler):
    def get(self):
        #XXX: returns a list of accepted NetTests
        pass

class HelperListHandler(web.RequestHandler):
    def get(self):
        #XXX: get the list of the running handlers
        #'id'
        #'description'
        #'address'
        pass

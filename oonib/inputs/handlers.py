from oonib.handlers import OONIBHandler

from oonib import config

import json
import os
import yaml

class InputsDescHandler(OONIBHandler):
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

class InputsListHandler(OONIBHandler):
    def get(self):
        if not config.main.input_dir: return
        path = os.path.abspath(config.main.input_dir) + "/*"
        inputnames = map(os.path.basename, glob.iglob(path))
        inputList = []
        for inputname in inputnames:
            f = open(os.path.join(config.main.input_dir, deckname))
            d = yaml.safe_load(f)
            inputList.append({
                'id': inputname,
                'name': d['name'],
                'description': d['description']
            })
            f.close()
        self.write(json.dumps(inputList))

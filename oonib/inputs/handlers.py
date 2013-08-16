import glob
import json
import os

import yaml

from oonib.handlers import OONIBHandler

from oonib import config

class InputsDescHandler(OONIBHandler):
    def get(self, inputID):
        #XXX return the input descriptor
        # see oonib.md in ooni-spec
        bn = os.path.basename(inputID) + ".desc"
        try:
            f = open(os.path.join(config.main.inputs_dir, bn))
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
        path = os.path.abspath(config.main.inputs_dir) + "/*"
        inputnames = map(os.path.basename, glob.iglob(path))
        inputList = []
        for inputname in inputnames:
            f = open(os.path.join(config.main.inputs_dir, inputname))
            d = yaml.safe_load(f)
            inputList.append({
                'id': inputname,
                'name': d['name'],
                'description': d['description']
            })
            f.close()
        self.write(json.dumps(inputList))

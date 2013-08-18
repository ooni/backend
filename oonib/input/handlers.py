import glob
import json
import os
import yaml

from oonib.handlers import OONIBHandler
from oonib import config, log

class InputDescHandler(OONIBHandler):
    def get(self, inputID):
        bn = os.path.basename(inputID) + ".desc"
        try:
            f = open(os.path.join(config.main.input_dir, bn))
            a = {}
            inputDesc = yaml.safe_load(f)
            for k in ['name', 'description', 'version', 'author', 'date']:
                a[k] = inputDesc[k]
            self.write(json.dumps(a))
        except IOError:
            log.err("No Input Descriptor found for id %s" % inputID) 
        except Exception, e:
            log.err("Invalid Input Descriptor found for id %s" % inputID) 

class InputListHandler(OONIBHandler):
    def get(self):
        path = os.path.abspath(config.main.input_dir) + "/*.desc"
        inputnames = map(os.path.basename, glob.iglob(path))
        inputList = []
        for inputname in inputnames:
            f = open(os.path.join(config.main.input_dir, inputname))
            d = yaml.safe_load(f)
            inputList.append({
                'id': inputname,
                'name': d['name'],
                'description': d['description']
            })
            f.close()
        self.write(json.dumps(inputList))

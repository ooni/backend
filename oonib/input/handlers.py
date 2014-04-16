import glob
import json
import os
import yaml

from oonib.handlers import OONIBHandler
from oonib import log
from oonib.config import config

class InputDescHandler(OONIBHandler):
    def get(self, inputID):
        bn = os.path.basename(inputID) + ".desc"
        try:
            f = open(os.path.join(config.main.input_dir, bn))
        except IOError:
            log.err("No Input Descriptor found for id %s" % inputID) 
            self.set_status(404)
            self.write({'error': 'missing-input'})
            return
        with f:
            inputDesc = yaml.safe_load(f)
 
        response = {'id': inputID}
        for k in ['name', 'description', 'version', 'author', 'date']:
            try:
                response[k] = inputDesc[k]
            except Exception, e: # XXX this should probably be KeyError
                log.exception(e)
                log.err("Invalid Input Descriptor found for id %s" % inputID) 
                self.set_status(500)
                self.write({'error': 'invalid-input-descriptor'})
                return

        self.write(response)

class InputListHandler(OONIBHandler):
    def get(self):
        path = os.path.abspath(config.main.input_dir) + "/*.desc"
        inputnames = map(os.path.basename, glob.iglob(path))
        inputList = []
        for inputname in inputnames:
            with open(os.path.join(config.main.input_dir, inputname)) as f:
                d = yaml.safe_load(f)
                inputList.append({
                    'id': inputname,
                    'name': d['name'],
                    'description': d['description']
                })
        self.write(inputList)

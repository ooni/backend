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
            with open(os.path.join(config.main.input_dir, bn)) as f:
                response = {}
                inputDesc = yaml.safe_load(f)
                for k in ['name', 'description', 'version', 'author', 'date']:
                    response[k] = inputDesc[k]
                response['id'] = inputID
            self.write(response)
        except IOError:
            log.err("No Input Descriptor found for id %s" % inputID) 
            self.set_status(404)
            self.write({'error': 'missing-input'})
 
        except Exception, e:
            log.exception(e)
            log.err("Invalid Input Descriptor found for id %s" % inputID) 
            self.set_status(500)
            self.write({'error': 'invalid-input-descriptor'})

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

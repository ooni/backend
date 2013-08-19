import glob
import json
import os
import yaml

from oonib.handlers import OONIBHandler
from oonib import config, log

class NetTestDescHandler(OONIBHandler):
    def get(self, netTestID):
        bn = os.path.basename(netTestID) + ".desc"
        try:
            with open(os.path.join(config.main.nettest_dir, bn)) as f:
                response = {}
                netTestDesc = yaml.safe_load(f)
                for k in ['name', 'description', 'version', 'author', 'date']:
                    response[k] = netTestDesc[k]
            self.write(response)
        except IOError:
            log.err("No NetTest Descriptor found for id %s" % netTestID) 
            self.set_status(404)
            self.write({'error': 'missing-nettest'})
 
        except Exception, e:
            log.err("Invalid NetTest Descriptor found for id %s" % netTestID) 
            self.set_status(500)
            self.write({'error': 'invalid-nettest-descriptor'})

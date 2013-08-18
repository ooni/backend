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
            f = open(os.path.join(config.main.nettest_dir, bn))
            a = {}
            netTestDesc = yaml.safe_load(f)
            for k in ['name', 'description', 'version', 'author', 'date']:
                a[k] = netTestDesc[k]
            self.write(json.dumps(a))
        except IOError:
            log.err("No NetTest Descriptor found for id %s" % netTestID) 
        except Exception, e:
            log.err("Invalid NetTest Descriptor found for id %s" % netTestID) 




import json 
import random
import yaml
from oonib.handlers import OONIBHandler
from oonib import config

#knownHelpers = {'helper-name': ['collector-address1', 'collector-address2', ... 'collector-addressn']}
knownHelpers = {}

def updateKnownHelpers():
    with open(config.main.bouncer_file) as f:
        bouncerFile = yaml.safe_load(f)
        for collectorName, helpers in bouncerFile['collector'].items():
            for helperName, helperAddress in helpers['test-helper'].items():
                if helperName not in knownHelpers.keys():
                    knownHelpers[helperName] = []
              
                knownHelpers[helperName].append(
                        {'collector-name': collectorName,
                         'helper-address': helperAddress
                         })
updateKnownHelpers()

class BouncerQueryHandler(OONIBHandler):
    def get(self):
        #XXX unused
        pass

    def post(self):
        helpers = json.loads(self.request.body)['test-helpers']
        a = {}
        a['collector'] = {}
        for helperName in helpers:
            if helperName in knownHelpers.keys():
                chosen = random.choice(knownHelpers[helperName])
                collectorName, helperAddress = chosen['collector-name'], chosen['helper-address']
                if not collectorName in a['collector'].keys():
                    a['collector'][collectorName] = {'test-helper': {}}
                a['collector'][collectorName]['test-helper'][helperName] = helperAddress
        self.write(json.dumps(a))

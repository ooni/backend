import json 
import random
import yaml
from oonib.handlers import OONIBHandler
from oonib import config

class BouncerQueryHandler(OONIBHandler):
    def initialize(self):
        self.knownHelpers = {}
        self.updateKnownHelpers()

    def updateKnownHelpers(self):
        with open(config.main.bouncer_file) as f:
            bouncerFile = yaml.safe_load(f)
            for collectorName, helpers in bouncerFile['collector'].items():
                for helperName, helperAddress in helpers['test-helper'].items():
                    if helperName not in self.knownHelpers.keys():
                        self.knownHelpers[helperName] = []
                  
                    self.knownHelpers[helperName].append({
                        'collector-name': collectorName,
                        'helper-address': helperAddress
                    })

    def post(self):
        try:
            query = json.loads(self.request.body)
        except ValueError:
            self.set_status(400)
            self.write(json.dumps({'error': 'invalid-request'}))
            return

        try:
            helpers = query['test-helpers']
        except KeyError:
            self.set_status(400)
            self.write(json.dumps({'error': 'test-helpers-key-missing'}))
            return

        response = {}
        response['collector'] = {}
        for helperName in helpers:
            if helperName in self.knownHelpers.keys():
                chosen = random.choice(self.knownHelpers[helperName])
                collectorName, helperAddress = chosen['collector-name'], chosen['helper-address']
                if not collectorName in response['collector'].keys():
                    response['collector'][collectorName] = {'test-helper': {}}
                response['collector'][collectorName]['test-helper'][helperName] = helperAddress

        self.write(response)

import json 
import random
import yaml
from oonib.handlers import OONIBHandler
from oonib import config

class Bouncer(object):
    def __init__(self):
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

    def getHelperAddresses(self, helper_name):
        """
        Returns a dict keyed on the collector address of known test helpers.
        example:
         {
            'httpo://thirteenchars1.onion': '127.0.0.1',
            'httpo://thirteenchars2.onion': '127.0.0.2',
            'httpo://thirteenchars3.onion': '127.0.0.3'
         }
        """
        try:
            helpers = self.knownHelpers[helper_name]
        except KeyError:
            raise e.NoHelperFound
        
        helpers_dict = {}
        for helper in helpers:
            helpers_dict[helper['collector-name']] = helper['helper-address']

        return helpers_dict
    
    def filterHelperAddresses(self, requested_helpers):
        """
        Returns a dict of collectors that support all the requested_helpers.

        Example:
        requested_helpers = ['a', 'b', 'c']
        will return:
         {
            'httpo://thirteenchars1.onion': {
                'a': '127.0.0.1',
                'b': 'http://127.0.0.1',
                'c': '127.0.0.1:590',
            }
         }

        """
        result = {}
        for helper_name in requested_helpers:
            for collector, helper_address in self.getHelperAddresses(helper_name).items():
                if collector not in result.keys():
                    result[collector] = {}
                result[collector][helper_name] = helper_address
        return result

class BouncerQueryHandler(OONIBHandler):
    def initialize(self):
        self.bouncer = Bouncer()

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
            raise e.InvalidRequest

        try:
            requested_helpers = query['test-helpers']
        except KeyError:
            raise e.TestHelpersKeyMissing

        response = {}
        response['collector'] = self.bouncer.filterHelperAddresses(requested_helpers)
        self.write(response)

import json 
import random
import yaml
from oonib import errors as e
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
            raise e.TestHelperNotFound
        
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
            'a': {
                'address': '127.0.0.1',
                'collector': 'httpo://thirteenchars1.onion'
            },
            'b': {
                'address': '127.0.0.1:8081',
                'collector': 'httpo://thirteenchars1.onion'
            },
            'c': {
                'address': 'http://127.0.0.1',
                'collector': 'httpo://thirteenchars2.onion'
            },
            'default': {
                'collector': 'httpo://thirteenchars1.onion'
            }
         }

         or 

         {'error': 'test-helper-not-found'}

         if no valid helper was found

        """
        result = {}
        for helper_name in requested_helpers:
            for collector, helper_address in self.getHelperAddresses(helper_name).items():
                if collector not in result.keys():
                    result[collector] = {}
                result[collector][helper_name] = helper_address

        # {
        #   'foo.onion': {'some-helper': 'some-address'},
        #   'foo2.onion': {'some-helper': 'some-addres2'}
        # }

        response = {}
        default_collector = None
        max_helper_count = 0
        for collector, helpers in result.items():
            if len(helpers) > max_helper_count:
                default_collector = collector
            else:
                continue

        response['default'] = {}
        response['default']['collector'] = default_collector

        if not len(result[default_collector]) == len(requested_helpers):
            found_helpers = set(result[default_collector].items())
            for missing_helper in found_helpers.difference(requested_helpers):
                collector, address = random.choice(self.getHelperAddress(missing_helper).items())
                response[missing_helper] = {}
                response[missing_helper]['collector'] = collector
                response[missing_helper]['address'] = address

        for name, address in result[default_collector].items():
            response[name] = {}
            response[name]['address'] = address
            response[name]['collector'] = default_collector
        
        return response

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

        response = self.bouncer.filterHelperAddresses(requested_helpers)
        self.write(response)

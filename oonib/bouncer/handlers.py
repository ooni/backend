import json 
import random
import yaml
from oonib import errors as e
from oonib.handlers import OONIBHandler
from oonib.config import config

class Bouncer(object):
    def __init__(self):
        with open(config.main.bouncer_file) as f:
            bouncerFile = yaml.safe_load(f)
        self.updateKnownHelpers(bouncerFile)
        self.updateKnownCollectors(bouncerFile)

    def updateKnownCollectors(self, bouncerFile):
        """
        Initialize the list of all known collectors
        """
        self.knownCollectors = []
        for collectorName, helpers in bouncerFile['collector'].items():
            if collectorName not in self.knownCollectors:
                self.knownCollectors.append(collectorName)
        
    def updateKnownHelpers(self, bouncerFile):
        self.knownHelpers = {}
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
        response = {}
        for helper_name in requested_helpers:
            try:
                # If we can, try to pick the same collector.
                choices = self.getHelperAddresses(helper_name)
                for item in response.values():
                    c = item['collector']
                    if c in choices:
                        break
                # Or default to a random selection
                else:
                    c = random.choice(choices)

                response[helper_name] = {'collector': c, 'address': choices[c]}

            except e.TestHelperNotFound:
                response = {'error': 'test-helper-not-found'}
                return response

        response['default'] = {'collector': random.choice(self.knownCollectors)}
        return response

class BouncerQueryHandler(OONIBHandler):
    def initialize(self):
        self.bouncer = Bouncer()

    def post(self):
        try:
            query = json.loads(self.request.body)
        except ValueError:
            raise e.InvalidRequest

        try:
            requested_helpers = query['test-helpers']
        except KeyError:
            raise e.TestHelpersKeyMissing
        
        try:
            assert isinstance(requested_helpers, list)
        except AssertionError:
            raise e.InvalidRequest

        response = self.bouncer.filterHelperAddresses(requested_helpers)
        self.write(response)

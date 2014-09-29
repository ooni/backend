import json
import yaml
import random
from oonib import errors as e
from oonib.handlers import OONIBHandler
from oonib.config import config


class Bouncer(object):

    def __init__(self, bouncer_file):
        self.bouncerFilename = bouncer_file
        self.load()

    def load(self):
        with open(self.bouncerFilename) as f:
            self.bouncerFile = yaml.safe_load(f)
        self.updateKnownHelpers()
        self.updateKnownCollectors()

    def updateKnownCollectors(self):
        """
        Initialize the list of all known collectors
        """
        self.knownCollectorsWithPolicy = []
        self.knownCollectorsWithoutPolicy = []
        for collectorName, content in self.bouncerFile['collector'].items():
            if content.get('policy') is not None and \
                    collectorName not in self.knownCollectorsWithPolicy:
                self.knownCollectorsWithPolicy.append(collectorName)
            elif content.get('policy') is None and \
                    collectorName not in self.knownCollectorsWithoutPolicy:
                self.knownCollectorsWithoutPolicy.append(collectorName)

    def updateKnownHelpers(self):
        self.knownHelpers = {}
        for collectorName, helpers in self.bouncerFile['collector'].items():
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
                    c = random.choice(choices.keys())

                response[helper_name] = {'collector': c, 'address': choices[c]}

            except e.TestHelperNotFound:
                response = {'error': 'test-helper-not-found'}
                return response

        if len(self.knownCollectorsWithoutPolicy) > 0:
            default_collector = random.choice(
                self.knownCollectorsWithoutPolicy)
        else:
            default_collector = None
        response['default'] = {'collector': default_collector}
        return response

    def collectorAccepting(self, net_test_name, input_hashes, test_helpers):
        for collector_address in self.knownCollectorsWithPolicy:
            collector = self.bouncerFile['collector'][collector_address]
            supported_net_tests = [x['name'] for x in
                                   collector['policy']['nettest']]
            supported_input_hashes = [x['id'] for x in
                                      collector['policy']['input']]
            if net_test_name not in supported_net_tests:
                continue
            if any([input_hash not in supported_input_hashes for input_hash in
                    input_hashes]):
                continue
            if all([x in collector['test-helper'].keys() for x in
                    test_helpers]):
                return collector_address
        if len(self.knownCollectorsWithoutPolicy) > 0:
            return random.choice(self.knownCollectorsWithoutPolicy)
        else:
            raise e.CollectorNotFound

    def filterByNetTests(self, requested_nettests):
        """
        Here we will return a list containing test helpers and collectors for
        the required nettests.
        We give favour to the collectors that have a stricter policy and if
        those fail we will resort to using the collectors with a more lax
        policy.
        """
        nettests = []
        for requested_nettest in requested_nettests:
            collector = self.collectorAccepting(
                requested_nettest['name'],
                requested_nettest['input-hashes'],
                requested_nettest['test-helpers'])
            test_helpers = {}
            for test_helper in requested_nettest['test-helpers']:
                test_helpers[test_helper] = self.bouncerFile['collector'][collector]['test-helper'][test_helper]

            nettest = {
                'name': requested_nettest['name'],
                'version': requested_nettest['version'],
                'input-hashes': requested_nettest['input-hashes'],
                'test-helpers': test_helpers,
                'collector': collector,
            }
            nettests.append(nettest)
        return {'net-tests': nettests}


class BouncerHandlerBase(OONIBHandler):
    def initialize(self):
        self.bouncer = Bouncer(config.main.bouncer_file)

    def load_query(self):
        if not 'query' in dir(self):
            try:
                self.query = json.loads(self.request.body)
            except ValueError:
                raise e.InvalidRequest


class BouncerTestHelpers(BouncerHandlerBase):
    def post(self):
        self.load_query()
        if 'test-helpers' in self.query:
            requested_helpers = self.query['test-helpers']
            if not isinstance(requested_helpers, list):
                raise e.InvalidRequest
            response = self.bouncer.filterHelperAddresses(requested_helpers)
        else:
            raise e.InvalidRequest

        self.write(response)


class BouncerNetTests(BouncerHandlerBase):
    def post(self):
        self.load_query()
        if 'net-tests' in self.query:
            response = self.bouncer.filterByNetTests(self.query['net-tests'])
        else:
            raise e.InvalidRequest

        self.write(response)


class BouncerQueryHandler(BouncerNetTests, BouncerTestHelpers):
    def post(self):
        self.load_query()
        if 'test-helpers' in self.query:
            BouncerTestHelpers.post(self)
        elif 'net-tests' in self.query:
            BouncerNetTests.post(self)
        else:
            raise e.TestHelpersOrNetTestsKeyMissing

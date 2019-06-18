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
            test_helpers_alternate = {}
            collector_info = self.bouncerFile['collector'][collector]
            for test_helper in requested_nettest['test-helpers']:
                try:
                    test_helpers[test_helper] = \
                        collector_info['test-helper'][test_helper]
                except KeyError:
                    helpers = self.knownHelpers.get(test_helper)
                    if not helpers:
                        raise e.CollectorNotFound
                    helper = random.choice(helpers)
                    test_helpers[test_helper] = helper['helper-address']

                try:
                    test_helpers_alternate[test_helper] = \
                        collector_info['test-helper-alternate'][test_helper]
                except KeyError:
                    pass

            nettest = {
                'name': requested_nettest['name'],
                'version': requested_nettest['version'],
                'input-hashes': requested_nettest['input-hashes'],
                'test-helpers': test_helpers,
                'test-helpers-alternate': test_helpers_alternate,
                'collector': collector,
                'collector-alternate': collector_info.get('collector-alternate', [])
            }
            nettests.append(nettest)
        return {'net-tests': nettests}

    def formatCollectorsWithoutPolicy(self):
        ''' Formats the collectors without policy for the new
            /api/v1/collectors endpoint. '''
        results = []
        for collector in self.knownCollectorsWithoutPolicy:
            results.append({'type': 'onion', 'address': collector})
            section = self.bouncerFile.get('collector')
            if not section: continue
            info = section.get(collector)
            if not info: continue
            for alt in info['collector-alternate']:
                r = self.format_alternate_address(alt)
                if r:
                    results.append(r)
        return self.remove_duplicates_list(results)

    def formatTestHelpersWithoutPolicy(self):
        ''' Formats the test helpers without policy for the new
            /api/v1/test-helpers endpoint. '''
        results = {}
        for collector in self.knownCollectorsWithoutPolicy:
            section = self.bouncerFile.get('collector')
            if not section: continue
            info = section.get(collector)
            if not info: continue
            helper = info.get('test-helper')
            if helper:
                for k, v in helper.items():
                    results.setdefault(k, []).append({
                        'type': 'legacy',
                        'address': v,
                    })
            alt = info.get('test-helper-alternate')
            if alt:
                for k, v in alt.items():
                    results.setdefault(k, [])
                    for e in v:
                        r = self.format_alternate_address(e)
                        if r:
                            results[k].append(r)
        return self.remove_duplicate_dict_values(results)

    @staticmethod
    def format_alternate_address(entry):
        res = {
            'type': entry.get('type'),
            'address': entry.get('address'),
            'front': entry.get('front'),
        }
        if not res['type'] or not res['address']:
            return None  # reject invalid input with missing mandatory fields
        if not res['front']:
            del res['front']  # make sure we do not emit a None optional field
        return res

    @staticmethod
    def remove_duplicates_list(alist):
        # Implementation note: dictionaries are non-hashable in python
        # so we remove duplicates using a slow approach
        #
        # See https://stackoverflow.com/a/7961390/4354461
        blist = []
        for elem in alist:
            if elem in blist:
                continue
            blist.append(elem)
        return blist

    def remove_duplicate_dict_values(self, adict):
        for key in adict.keys():
            adict[key] = self.remove_duplicates_list(adict[key])
        return adict


class APIv1Collectors(OONIBHandler):
    def initialize(self):
        self.bouncer = Bouncer(config.main.bouncer_file)

    def get(self):
        self.write(self.bouncer.formatCollectorsWithoutPolicy())


class APIv1TestHelpers(OONIBHandler):
    def initialize(self):
        self.bouncer = Bouncer(config.main.bouncer_file)

    def get(self):
        self.write(self.bouncer.formatTestHelpersWithoutPolicy())


class BouncerHandlerBase(OONIBHandler):
    def initialize(self):
        self.bouncer = Bouncer(config.main.bouncer_file)

    def load_query(self):
        if 'query' not in dir(self):
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

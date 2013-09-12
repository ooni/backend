from oonib import errors as e
from oonib.handlers import OONIBHandler

from oonib import config
import json
import os
import yaml

class Policy(object):
    nettest = None
    input = None

    def __init__(self):
        with open(config.main.policy_file) as f:
            p = yaml.safe_load(f)
            self.input = self.nettest = []
            if 'nettest' in p.keys():
                self.nettest = list(p['nettest'])
            if 'input' in p.keys():
                self.input = list(p['input'])

    def validateInputHash(self, input_hash):
        valid = False
        if not self.input:
            valid = True
        for i in self.input:
            if input_hash == i['id']:
                valid = True
                break
        if not valid:
            raise e.InvalidInputHash

    def validateNettest(self, nettest_name):
        # XXX add support for version checking too.
        valid = False
        if self.nettest:
            valid = True
        for nt in self.nettest:
            if nettest_name == nt['name']:
                valid = True
                break
        if not valid:
            raise e.InvalidNettestName

class PolicyHandler(OONIBHandler):
    def initialize(self):
        self.policy = Policy()

class NetTestPolicyHandler(PolicyHandler):
    def get(self):
        """
        returns a list of accepted NetTests
        """
        self.write(self.policy.nettest)

class InputPolicyHandler(PolicyHandler):
    def get(self):
        """
        return list of input ids
        """
        self.write(self.policy.input)


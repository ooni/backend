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
            self.nettest = list(p['nettest'])
            self.input = list(p['input'])

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


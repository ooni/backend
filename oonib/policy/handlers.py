from oonib.handlers import OONIBHandler

from oonib import config
import json
import os
import yaml

class NetTestPolicyHandler(OONIBHandler):
    def get(self):
        """
        returns a list of accepted NetTests
        """
        with open(config.main.policy_file) as f:
            p = yaml.safe_load(f)
            self.write(json.dumps(p['nettest']))

class InputPolicyHandler(OONIBHandler):
    def get(self):
        """
        return list of input ids
        """
        with open(config.main.policy_file) as f:
            p = yaml.safe_load(f)
            self.write(json.dumps(p['input']))

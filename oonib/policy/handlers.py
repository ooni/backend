from oonib.api import OONIBHandler

from oonib import config
import json
import os
import yaml

class NetTestPolicyHandler(OONIBHandler):
    def get(self):
        """
        returns a list of accepted NetTests
        """
        pass

class InputPolicyHandler(OONIBHandler):
    def get(self):
        """
        return list of input ids
        """
        pass

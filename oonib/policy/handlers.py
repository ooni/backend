from cyclone import web
from oonib import config
import json
import os
import yaml

class NetTestPolicyHandler(web.RequestHandler):
    def get(self):
        #XXX: returns a list of accepted NetTests
        pass

class InputPolicyHandler(web.RequestHandler):
    def get(self):
        pass
        #XXX return list of input ids

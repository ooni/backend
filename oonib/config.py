import yaml
from oonib import errors as e
from oonib import Storage
from oonib import __version__

from oonib.options import OONIBOptions
import os

class Config(object):
    main = None
    helpers = None
    reports = {}
    backend_version = __version__
    opts = OONIBOptions()

    def __init__(self):
        self.opts.parseOptions()

    def load(self):
        try:
            config_file = self.opts['config']
        except KeyError:
            raise e.ConfigFileNotSpecified

        try:
            with open(self.opts['config']) as f:
                configuration = yaml.safe_load(f)
        except IOError:
            raise e.ConfigFileDoesNotExist(self.opts['config'])

        self.main = Storage()
        for k, v in configuration['main'].items():
            self.main[k] = v
        self.helpers = Storage()
        for name, helper in configuration['helpers'].items():
            self.helpers[name] = Storage()
            for k, v in helper.items():
                self.helpers[name][k] = v
        self.check_paths()
    
    def check_paths(self):
        def check_path(directory, complaint):
            if not (directory and os.path.isdir(directory)):
                raise complaint(directory)
        check_path(self.main.report_dir,  e.InvalidReportDirectory)
        check_path(self.main.archive_dir, e.InvalidArchiveDirectory)
        check_path(self.main.input_dir,   e.InvalidInputDirectory)
        check_path(self.main.deck_dir,    e.InvalidDeckDirectory)

backend_version = __version__
reports = {}

config = Config()

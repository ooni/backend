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
            with open(config_file) as f:
                configuration = yaml.safe_load(f)
        except IOError:
            raise e.ConfigFileDoesNotExist(config_file)

        self.main = Storage(configuration['main'].items())

        self.helpers = Storage()
        for name, helper in configuration['helpers'].items():
            self.helpers[name] = Storage(helper.items())

        self.check_paths()
    
    def check_paths(self):
        if not self.main.report_dir or not os.path.isdir(self.main.report_dir):
            raise e.InvalidReportDirectory(self.main.report_dir)
        if not self.main.archive_dir or not os.path.isdir(self.main.archive_dir):
            raise e.InvalidArchiveDirectory(self.main.archive_dir)

backend_version = __version__

config = Config()

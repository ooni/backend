import yaml
from oonib import errors as e
from oonib import Storage
from oonib import __version__

from oonib.options import OONIBOptions
import os


class Config(object):
    backend_version = __version__
    opts = OONIBOptions()

    def __init__(self):
        self.main = Storage()
        self.helpers = Storage()
        self.reports = Storage()

    def load(self):
        self.opts.parseOptions()
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
        if self.main.logfile is None:
            self.main.logfile = 'oonib.log'

        self.helpers = Storage()
        for name, helper in configuration['helpers'].items():
            self.helpers[name] = Storage(helper.items())

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

config = Config()

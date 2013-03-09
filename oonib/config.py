import yaml
from oonib import Storage

from oonib.options import OONIBOptions
import os

def get_root_path():
    this_directory = os.path.dirname(__file__)
    root = os.path.join(this_directory, '..')
    root = os.path.abspath(root)
    return root

def loadConfigFile():
    opts = OONIBOptions()
    opts.parseOptions()
    if 'config' in opts.keys():
        with open(opts['config']) as f:
            config_file_contents = '\n'.join(f.readlines())
            configuration = yaml.safe_load(config_file_contents)
            main = Storage(opts)
            for k, v in configuration['main'].items():
                main[k] = v
            helpers = Storage()
            for k, v in configuration['helpers'].items():
                helpers[k] = Storage()
                for k2, v2 in v.items():
                    helpers[k][k2] = v2
            return main, helpers
    return None, None

main = None

if not main:
    main, helpers = loadConfigFile()

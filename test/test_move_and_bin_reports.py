import os
import shutil
import logging
from invoke.config import Config
from pipeline.batch import move_and_bin_reports

config = Config(runtime_path="../invoke.yaml")
assert config._runtime_found, "you probably need to 'cp invoke.yaml.example invoke.yaml'"
logger = logging.getLogger('ooni-pipeline')

# this tests that a file is moved and renamed
# XXX todo: make proper test, this fails because invoke config blah blah

#├── incoming
#│   └── http_invalid_request_line-2015-06-29T142714Z-AS201227-probe.yamloo
#├── private
# invoke move_and_bin_reports --src test/incoming/ --dst test/private/
#├── incoming
#├── private
#│   └── 2015-06-29
#│       └── 20150629T142714Z-AS201227-http_invalid_request_line-v1-probe.yaml


src_dir = 'incoming'
dst_dir = 'private'
dst_subdir = '2015-06-29'

in_filename = 'http_invalid_request_line-2015-06-29T142714Z-AS201227-probe.yamloo'
out_filename = '20150629T142714Z-AS201227-http_invalid_request_line-v1-probe.yaml'

try:
    shutil.rmtree(os.path.join(dst_dir, dst_subdir))
except OSError:
    pass



in_file = open(os.path.join(src_dir, in_filename), 'w')
in_file.write('dummy file')
in_file.close()

move_and_bin_reports.run(src_directory=src_dir, dst=dst_dir)

out_file = open(os.path.join(dst_dir, dst_subdir, out_filename), 'r')
out_contents = out_file.read()
out_file.close()

assert out_contents == 'dummy file'

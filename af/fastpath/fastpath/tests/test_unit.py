#
# Fastpath - unit tests
#

import fastpath.fastpath as fp
import fastpath.s3feeder as s3feeder
import fastpath.s3uploader as s3uploader


def test_reset_status():
    clear = 0
    cleared_from_now = 2
    blocked = 1
    blocked_from_now = 3
    status = dict(a=clear, b=cleared_from_now, c=blocked, d=blocked_from_now)
    fp.reset_status(status)
    assert status == dict(c=blocked, d=blocked)

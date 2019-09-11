#
# Fastpath - unit tests
#

import fastpath.core as fp
import fastpath.normalize as normalize
import ujson


def test_reset_status():
    clear = 0
    cleared_from_now = 2
    blocked = 1
    blocked_from_now = 3
    status = dict(a=clear, b=cleared_from_now, c=blocked, d=blocked_from_now)
    fp.reset_status(status)
    assert status == dict(c=blocked, d=blocked)


def test_pack():
    # s3uploader.pack(dict(a=1, b=[[dict(z=[b"zz"])]]))
    pass


def test_trivial_id():
    msm_jstr, tid = fp.trivial_id(dict(a="🐱"))
    assert len(tid) == 32
    assert tid == "00d1cb49bba274be952c9f701f1e13b8"


def test_trivial_id_2():
    with open("fastpath/tests/data/report_real.json") as f:
        msm = ujson.load(f)
    msm_jstr, tid = fp.trivial_id(msm)
    assert tid == "00b236a79311d1239838bb7431955592"

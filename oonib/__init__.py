# -*- encoding: utf-8 -*-
#
# :authors: Arturo Filastò, Isis Lovecruft
# :licence: see LICENSE for details
"""
In here we shall keep track of all variables and objects that should be
instantiated only once and be common to pieces of GLBackend code.
"""

from twisted.python.threadpool import ThreadPool

from storm.uri import URI
from storm.twisted.transact import Transactor
from storm.databases.sqlite import SQLite
import string
import random

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions

__all__ = ['database', 'db_threadpool', 'Storage', 'randomStr']


class Storage(dict):
    """
    A Storage object is like a dictionary except `obj.foo` can be used
    in addition to `obj['foo']`.

        >>> o = Storage(a=1)
        >>> o.a
        1
        >>> o['a']
        1
        >>> o.a = 2
        >>> o['a']
        2
        >>> del o.a
        >>> o.a
        None
    """
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError, k:
            return None

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError, k:
            raise AttributeError, k

    def __repr__(self):
        return '<Storage ' + dict.__repr__(self) + '>'

    def __getstate__(self):
        return dict(self)

    def __setstate__(self, value):
        for (k, v) in value.items():
            self[k] = v

def randomStr(length, num=True):
    """
    Returns a random a mixed lowercase, uppercase, alfanumerical (if num True)
    string long length
    """
    chars = string.ascii_lowercase + string.ascii_uppercase
    if num:
        chars += string.digits
    return ''.join(random.choice(chars) for x in range(length))

from oonib import config

database = SQLite(URI(config.main.database_uri))
db_threadpool = ThreadPool(0, config.main.db_threadpool_size)
db_threadpool.start()
transactor = Transactor(db_threadpool)


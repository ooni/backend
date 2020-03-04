# -*- coding: utf-8 -*-
"""
Portable multiprocessing queue singleton
"""

import multiprocessing as mp

# Queue.qsize() is not reliable - and absent under OSX
# Implement a queue as a singleton with locking around the queue size

_q = mp.Queue()  # type: mp.queues.Queue
_size = mp.Value("i", 0)


def put(val):
    with _size.get_lock():
        _size.value += 1
        _q.put(val)


def get():
    # get() blocks until a message arrives and cannot be done in the lock
    # otherwise a reader can block any writer
    # Warning: race condition. After the get() the real queue is smaller than
    # qsize() but this is OK as we only check "if qsize() > threshold" to
    # throttle the writer
    v = _q.get()
    with _size.get_lock():
        _size.value -= 1
    return v


def qsize():
    with _size.get_lock():
        return _size.value

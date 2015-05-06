from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import threading

from concurrent import futures


def wrap_in_future(func):
    result = futures.Future()
    try:
        result.set_result(func())
    except Exception as err:
        result.set_exception(err)

    return result


class BlockingPool(object):
    def __init__(self, max_workers):
        self._pool = futures.ThreadPoolExecutor(max_workers)
        self._lock = threading.RLock()
        self._running = {}

    def run(self, key, job):
        with self._lock:
            try:
                return self._running[key]

            except KeyError:
                fast_result = wrap_in_future(job.fast)
                if not fast_result.exception():
                    return fast_result

                # run job on pool
                future = self._pool.submit(job.slow)
                self._running[key] = future
                future.add_done_callback(lambda f: self._remove(key))
                return future

    def _remove(self, key):
        with self._lock:
            self._running.pop(key)

    @property
    def running_count(self):
        with self._lock:
            return len(self._running)


class FileJob(object):
    def __init__(self, target, func):
        self.target = target
        self.func = func

    def fast(self):
        if not self.target.exists():
            raise IOError("file {} not found".format(self.target))

        return self.target

    def slow(self):
        self.func()
        return self.target

import json
import time
import traceback
from datetime import datetime
from multiprocessing import Process, Semaphore, JoinableQueue


class BaseNode(object):
    def __init__(self, concurrency=1, fail_log_filename="fail.log", *args,
                 **kw):
        self.concurrency = concurrency

        self.input_queue = JoinableQueue()
        self.output_queue = JoinableQueue()

        if fail_log_filename:
            self.fail_log = open(fail_log_filename, "a+")

        self.processes = []

        self.semaphore = Semaphore(concurrency)

        self.pipes = []
        self.start_time = None
        self.initialize(*args, **kw)

    def initialize(self):
        pass

    def finished(self):
        self.fail_log.close()
        self.log("Finished %s" % self)

    def log(self, msg):
        print("%s: %s" % (datetime.now(), msg))

    def failed(self, data, tb):
        self.log("Failed to process %s" % data)
        print(tb)
        if not self.fail_log:
            return
        payload = {
            "data": data,
            "traceback": tb
        }
        self.fail_log.write(json.dumps(payload))
        self.fail_log.write("\n")
        self.fail_log.flush()

    def send(self, data):
        for pipe in self.pipes:
            pipe.semaphore.acquire()
            self.output_queue.put(data)

    def into(self, pipe):
        pipe.input_queue = self.output_queue
        self.pipes.append(pipe)

    def start(self):
        self.start_time = time.time()
        for _ in xrange(self.concurrency):
            p = Process(target=self._consume_input)
            self.processes.append(p)
            p.start()

        for pipe in self.pipes:
            pipe.start()

    def done(self):
        for pipe in self.pipes:
            pipe.input_queue.join()
            pipe.finished()


class Emitter(BaseNode):
    def emit(self):
        raise NotImplemented

    def _consume_input(self):
        for data in self.emit():
            self.send(data)
        self.done()


class Pipe(BaseNode):
    def process(self, data):
        raise NotImplemented()

    def _run_process(self, data):
        output = self.process(data)
        try:
            items = iter(output)
        except TypeError:
            return self.send(output)

        for output in items:
            self.send(output)

    def _consume_input(self):
        while True:
            data = self.input_queue.get()
            try:
                self._run_process(data)
            except Exception:
                self.failed(data, traceback.format_exc())

            self.semaphore.release()
            self.input_queue.task_done()

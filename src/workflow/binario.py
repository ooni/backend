import time
from datetime import datetime
from multiprocessing import Process, Semaphore, Queue


class BaseNode(object):
    def __init__(self, concurrency=1):
        self.concurrency = concurrency

        self.input_queue = Queue()
        self.output_queue = Queue()

        self.semaphore = Semaphore(concurrency)

        self.pipes = []
        self.start_time = None
        self.initialize()

    def log(self, msg):
        print("%s: %s" % (datetime.now(), msg))

    def send(self, data):
        for pipe in self.pipes:
            pipe.semaphore.acquire()
            self.output_queue.put(data)
            pipe.receive()

    def into(self, pipe):
        pipe.input_queue = self.output_queue
        self.pipes.append(pipe)


class Emitter(BaseNode):
    def emit(self):
        for i in xrange(100):
            yield i

    def _consume_input(self):
        for data in self.emit():
            self.send(data)

    def start(self):
        consumer_process = Process(target=self._consume_input)
        self._start_time = time.time()
        consumer_process.start()


class Pipe(BaseNode):
    def process(self, data):
        raise NotImplemented()

    def _run_process(self):
        data = self.input_queue.get()
        for output in self.process(data):
            self.send(output)
        self._processed()

    def _processed(self):
        self.semaphore.release()

    def receive(self):
        p = Process(target=self._run_process)
        p.start()

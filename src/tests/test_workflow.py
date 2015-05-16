from workflow.binario import Pipe, Emitter

class Pipe1(Pipe):
    def process(self, data):
        yield str(data) + "_pipe1"


class Pipe2(Pipe):
    def process(self, data):
        yield str(data) + "_pipe2"


class Pipe3(Pipe):
    def process(self, data):
        output = str(data) + "_pipe3"
        print output
        yield output


def test_three_step_workflow():
    emitter = Emitter(1)

    first_step = Pipe1(10)
    second_step = Pipe2(10)
    third_step = Pipe3(10)

    first_step.into(second_step)
    second_step.into(third_step)

    emitter.into(first_step)
    emitter.start()

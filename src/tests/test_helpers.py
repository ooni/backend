from helpers.report import ReportStreamEmitter


def test_report_stream_emitter():
    emitter = ReportStreamEmitter('test')
    for report in emitter.emit():
        print report

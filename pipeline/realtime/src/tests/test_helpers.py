from helpers.report import ReportStreamEmitter


def test_report_stream_emitter():
    record_types = {
        "header": 0,
        "entry": 0,
        "footer": 0,
    }
    emitter = ReportStreamEmitter('test')
    for sr, rr in emitter.emit():
        record_types[sr["record_type"]] += 1
        record_types[rr["record_type"]] += 1
    assert record_types["header"] == 2
    assert record_types["footer"] == 2
    assert record_types["entry"] == 6

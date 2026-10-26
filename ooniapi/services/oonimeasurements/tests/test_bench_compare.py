from .bench import compare


def _run(read_bytes):
    return {
        "queries": {
            "q": {"read_bytes": read_bytes, "read_rows": 1, "median_ms": 1.0, "response_hash": "h"}
        }
    }


def _row(base_bytes, new_bytes):
    [row] = compare.compare(_run(base_bytes), _run(new_bytes))
    return row


def test_reads_where_base_read_nothing():
    row = _row(0, 1_000_000)
    assert row["verdict"] == "reads more"
    assert "reads where base read nothing" in compare._change_note(row, None, plain=True)


def test_reads_nothing_where_base_read():
    row = _row(1_000_000, 0)
    assert row["verdict"] == "reads less"
    assert "reads nothing" in compare._change_note(row, None, plain=True)


def test_nothing_read_on_either_side_is_unchanged():
    row = _row(0, 0)
    assert row["verdict"] == ""
    assert compare._change_note(row, None, plain=True) == ""


def test_ratio_of_nonzero_reads():
    assert _row(1_000_000, 500_000)["verdict"] == "reads less"
    assert _row(1_000_000, 2_000_000)["verdict"] == "reads more"
    assert _row(1_000_000, 1_050_000)["verdict"] == ""

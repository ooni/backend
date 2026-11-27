import io

import pytest

from reuploader import main


class FakeS3:
    """The calls main() makes on a boto3 S3 client, over a dict of key -> body"""

    def __init__(self, objects):
        self.objects = dict(objects)

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix, Delimiter):
        subs, contents = set(), []
        for key in sorted(self.objects):
            if not key.startswith(Prefix):
                continue
            rest = key[len(Prefix):]
            if Delimiter in rest:
                subs.add(Prefix + rest.split(Delimiter)[0] + Delimiter)
            else:
                contents.append({"Key": key})
        yield {"CommonPrefixes": [{"Prefix": p} for p in sorted(subs)], "Contents": contents}

    def get_object(self, Bucket, Key):
        body = io.BytesIO(self.objects[Key])
        body.iter_chunks = lambda chunk_size: iter([body.read()])
        return {"Body": body}

    def delete_object(self, Bucket, Key):
        del self.objects[Key]


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.posted = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, data, headers, timeout):
        b"".join(data)
        self.posted.append(url.rsplit("/", 1)[-1])
        return FakeResponse()


OBJECTS = {
    "postcans/2026101320/2026101320_IT_webconnectivity/20261013200000.000001_IT_webconnectivity_aaaa.post": b"{}",
    "postcans/2026101320/2026101320_IT_webconnectivity/notes.txt": b"x",
    "dedup/postcans/2026101320/2026101320_IT_webconnectivity/20261013200000.000002_IT_webconnectivity_bbbb.post": b"{}",
}


@pytest.fixture
def run(monkeypatch):
    def run(prefix, objects=OBJECTS):
        s3, session = FakeS3(objects), FakeSession()
        monkeypatch.setattr(main, "BUCKET_NAME", "failed")
        monkeypatch.setattr(main, "FASTPATH_API", "http://fastpath:8472")
        monkeypatch.setattr(main, "PREFIX", prefix)
        monkeypatch.setattr(main, "get_s3_client", lambda: s3)
        monkeypatch.setattr(main.requests, "Session", lambda: session)
        main.main()
        return s3, session
    return run


def test_only_walks_the_prefix(run):
    s3, session = run("postcans/")
    assert session.posted == ["20261013200000.000001_IT_webconnectivity_aaaa"]
    assert sorted(s3.objects) == [
        "dedup/postcans/2026101320/2026101320_IT_webconnectivity/20261013200000.000002_IT_webconnectivity_bbbb.post",
        "postcans/2026101320/2026101320_IT_webconnectivity/notes.txt",
    ]


def test_no_prefix_walks_the_bucket(run):
    s3, session = run("")
    assert sorted(session.posted) == [
        "20261013200000.000001_IT_webconnectivity_aaaa",
        "20261013200000.000002_IT_webconnectivity_bbbb",
    ]
    assert list(s3.objects) == ["postcans/2026101320/2026101320_IT_webconnectivity/notes.txt"]

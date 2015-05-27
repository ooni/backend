import base64
import json


def encode_basestring_ascii(o):
    try:
        return encode_basestring_ascii_orig(o)
    except UnicodeDecodeError:
        return json.dumps({"base64": base64.b64encode(o)})
encode_basestring_ascii_orig = json.encoder.encode_basestring_ascii
json.encoder.encode_basestring_ascii = encode_basestring_ascii


def json_default(o):
    if isinstance(o, set):
        return list(o)
    return {"error": "could-not-serialize %s" % str(o)}


def json_dump(data, fh):
    encoder = json.JSONEncoder(ensure_ascii=True, default=json_default)
    for chunk in encoder.iterencode(data):
        fh.write(chunk)


def json_dumps(data):
    encoder = json.JSONEncoder(ensure_ascii=True, default=json_default)
    return encoder.encode(data)

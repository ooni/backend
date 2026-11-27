"""Merge the public GET endpoints of several services' OpenAPI documents into
the one served at https://api.ooni.io/openapi.json.

Usage: merge_openapi.py oonimeasurements.json oonifindings.json > openapi.json
(each input is `app.openapi()` dumped from that service)
"""

import json
import re
import sys

# ops endpoints and the private /api/_/ UI endpoints are not for API users
DROP = re.compile(r"^/($|health|version|metrics|api/_/)")


def refs(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "$ref":
                acc.add(v.rsplit("/", 1)[-1])
            else:
                refs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            refs(v, acc)
    return acc


def merge(specs):
    out = {
        "openapi": "3.1.0",
        "info": {
            "title": "OONI API",
            "version": "1",
            "description": "Public read-only endpoints of the OONI API.",
        },
        "servers": [{"url": "https://api.ooni.io"}],
        "paths": {},
        "components": {"schemas": {}},
    }
    schemas = out["components"]["schemas"]
    for spec in specs:
        for path, ops in spec["paths"].items():
            if DROP.match(path) or "get" not in ops:
                continue
            if path in out["paths"]:
                sys.exit(f"path {path} is served by two services")
            out["paths"][path] = {"get": ops["get"]}
        for name, schema in spec.get("components", {}).get("schemas", {}).items():
            if name in schemas and schemas[name] != schema:
                sys.exit(f"schema {name} differs between services")
            schemas[name] = schema
    # keep only the schemas the kept paths reach
    used = refs(out["paths"], set())
    while True:
        more = refs({n: schemas[n] for n in used}, set(used))
        if more == used:
            break
        used = more
    out["components"]["schemas"] = {
        n: s for n, s in sorted(schemas.items()) if n in used
    }
    return out


if __name__ == "__main__":
    specs = []
    for path in sys.argv[1:]:
        with open(path) as f:
            specs.append(json.load(f))
    json.dump(merge(specs), sys.stdout, separators=(",", ":"))
    print()

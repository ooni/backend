import sys
import json

from fastapi.openapi.utils import get_openapi
from .main import app
from .__about__ import VERSION

if __name__ == "__main__":
    openapi = get_openapi(title="OONI Findings", version=VERSION, routes=app.routes)
    assert len(sys.argv) == 2, "must specify outfile file"
    with open(sys.argv[1], "w") as out_file:
        out_file.write(json.dumps(openapi))
        out_file.write("\n")

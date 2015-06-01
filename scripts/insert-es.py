from __future__ import print_function

from datetime import datetime
import json
import os
from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk

report_dir = "/data1/reports/"
output_dir = "/data1/processed/"

header_properties = {
    "annotations": {"type": "string"},
    "backend_version": {"type": "string"},
    "input": {"type": "string"},
    "input_hashes": {"type": "string"},
    "options": {"type": "string"},
    "probe_asn": {"type": "string"},
    "probe_cc": {"type": "string"},
    "probe_city": {"type": "string"},
    "probe_ip": {"type": "string"},
    "record_type": {"type": "string"},
    "report_id": {"type": "string"},
    "software_name": {"type": "string"},
    "software_version": {"type": "string"},
    "start_time": {"type": "float"},
    "timestamp": {
        "type": "date",
        "format": "yyyy-MM-dd HH:mm:ss"
    },
    "subargs": {"type": "string"},
    "test_helpers": {"type": "string"},
    "test_name": {"type": "string"},
    "test_version": {"type": "string"}
}


def list_reports():
    for filename in os.listdir(report_dir):
        if filename.endswith(".sanitised"):
            yield os.path.join(report_dir, filename)


def esify(data):
    print("XXX")
    output = {}
    for key in header_properties.keys():
        output[key] = data.get(key)
    if isinstance(output["options"], dict):
        output["options"] = output["options"].get("subargs")
    output["_id"] = data["report_id"]
    output["timestamp"] = datetime.fromtimestamp(data["start_time"])
    output["start_time"] = float(data["start_time"])
    print(output)
    return output


def parse_report(report_path):
    with open(report_path) as in_file:
        for line in in_file:
            data = json.loads(line.strip())
            try:
                data = json.loads(line.strip())
            except:
                pass
            if not data:
                continue
            if data["record_type"] == "header":
                yield esify(data)
            elif data["record_type"] == "entry":
                pass
            elif data["record_type"] == "footer":
                pass


def load_report(client, report_path):
    client.create(
        index='report',
        doc_type='header',
        body={
            "mappings": {
                "header": {
                    "_timestamp": {
                        "enabled": True,
                        "type": "date",
                        "format": "yyyy-MM-dd HH:mm:ss",
                        "store": True,
                        "path": "timestamp"
                    },
                    "properties": header_properties
                }
            }
        },
        ignore=409  # 409 - conflict
    )
    for ok, result in streaming_bulk(
            client,
            parse_report(report_path),
            index="report",
            doc_type="header"):
        action, result = result.popitem()
        doc_id = '/report/%s' % (result['_id'])
        if not ok:
            print('Failed to %s document %s: %r' % (action, doc_id, result))
        else:
            print(doc_id)
        client.indices.refresh(index='report')

if __name__ == "__main__":
    es = Elasticsearch(["manager.infra.ooni.nu"])
    for report_path in list_reports():
        load_report(es, report_path)
    es.indices.refresh(index='report')

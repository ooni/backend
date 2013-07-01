"""
/report

/pcap

This is the async pcap reporting system. It requires the client to have created
a report already, but can work independently from test progress.

"""
import random
import string
import json
import re
import os

from twisted.internet import reactor, defer

from cyclone import web

from oonib import otime
from oonib import randomStr

from oonib import config
from oonib.report import file_collector

def parseUpdateReportRequest(request):
    #db_report_id_regexp = re.compile("[a-zA-Z0-9]+$")

    # this is the regexp for the reports that include the timestamp
    report_id_regexp = re.compile("[a-zA-Z0-9_-]+$")

    # XXX here we are actually parsing a json object that could be quite big.
    # If we want this to scale properly we only want to look at the test_id
    # field.
    # We are also keeping in memory multiple copies of the same object. A lot
    # of optimization can be done.
    parsed_request = json.loads(request)
    try:
        report_id = parsed_request['report_id']
    except KeyError:
        raise MissingField('report_id')

    if not re.match(report_id_regexp, report_id):
        raise InvalidRequestField('report_id')

    return parsed_request

reportingBackendAPI = [
    (r"/report/([a-zA-Z0-9_\-]+)/close", file_collector.CloseReportHandlerFile),
    (r"/report", file_collector.NewReportHandlerFile),
    (r"/pcap", file_collector.PCAPReportHandler),
    (r"/deck/([a-z0-9]{40})$", web.StaticFileHandler, {"path": config.deck_dir}),
    (r"/input/([a-z0-9]{40})$", web.StaticFileHandler, {"path": config.input_dir}),
]

reportingBackend = web.Application(reportingBackendAPI, debug=True)

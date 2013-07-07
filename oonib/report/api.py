"""
/report

/pcap

This is the async pcap reporting system. It requires the client to have created
a report already, but can work independently from test progress.

"""
from oonib.report import handlers

reportAPI = [
    (r"/report/([a-zA-Z0-9_\-]+)/close", handlers.CloseReportHandlerFile),
    (r"/report", handlers.NewReportHandlerFile),
    (r"/pcap", file_collector.PCAPReportHandler),
]

from oonib.report import handlers

reportAPI = [
    (r"/report/([a-zA-Z0-9_\-]+)/close", handlers.CloseReportHandlerFile),
    (r"/report/([a-zA-Z0-9_\-]+)", handlers.UpdateReportHandlerFile),
    (r"/report", handlers.NewReportHandlerFile),
    (r"/pcap", handlers.PCAPReportHandler),
]

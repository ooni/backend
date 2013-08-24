from cyclone.web import HTTPError

class OONIBError(HTTPError):
    def __init__(self):
        pass

class InvalidRequest(OONIBError):
    pass

class NoHelperFound(OONIBError):
    status_code = 404
    log_message = 'no-helper-found'

class InvalidInputHash(OONIBError):
    status_code = 406
    log_message = 'invalid-input-hash'

class InvalidNettestName(OONIBError):
    status_code = 406
    log_message = 'invalid-nettest-name'

class InputHashNotProvided(OONIBError):
    status_code = 406
    log_message = 'input-hash-not-provided'

class InvalidRequestField(OONIBError):
    def __init__(self, field_name):
        self.status_code = 400
        self.log_message = "invalid-request-field %s" % field_name

class MissingRequestField(OONIBError):
    def __init__(self, field_name):
        self.status_code = 400
        self.log_message = "missing-request-field %s" % field_name

class MissingReportHeaderKey(OONIBError):
    def __init__(self, key):
        self.status_code = 406
        self.log_message = "missing-report-header-key %s" % key

class InvalidReportHeader(OONIBError):
    def __init__(self, key):
        self.status_code = 406
        self.log_message = "invalid-report-header %s" % key

class ReportNotFound(OONIBError):
    status_code = 404
    log_message = "report-not-found"

class NoValidCollector(OONIBError):
    pass

class TestHelpersKeyMissing(OONIBError):
    status_code = 400
    log_message = "test-helpers-key-missing"

class TestHelperNotFound(OONIBError):
    status_code = 400
    log_message = "test-helper-not-found"

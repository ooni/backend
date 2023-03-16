from cyclone.web import HTTPError


class OONIBError(HTTPError):
    status_code = 500
    log_message = 'oonib-error'

    def __init__(self, status_code=None, log_message=None):
        if status_code:
            self.status_code = status_code
        if log_message:
            self.log_message = log_message


class InvalidRequest(OONIBError):
    status_code = 400
    log_message = 'invalid-request'


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


class InputDescriptorNotFound(OONIBError):
    status_code = 404
    log_message = 'input-descriptor-not-found'


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


class MissingDeckKeys(OONIBError):
    status_code = 400
    log_message = "missing-deck-keys"


class MissingDeck(OONIBError):
    status_code = 400
    log_message = "missing-deck"


class NoDecksConfigured(OONIBError):
    status_code = 501
    log_message = "no-decks-configured"


class InvalidReportHeader(OONIBError):
    def __init__(self, key):
        self.status_code = 406
        self.log_message = "invalid-report-header %s" % key


class ReportNotFound(OONIBError):
    status_code = 404
    log_message = "report-not-found"


class CollectorNotFound(OONIBError):
    status_code = 404
    log_message = "collector-not-found"


class NoValidCollector(OONIBError):
    status_code = 400
    log_message = "no-valid-collector"


class TestHelpersKeyMissing(OONIBError):
    status_code = 400
    log_message = "test-helpers-key-missing"


class TestHelpersOrNetTestsKeyMissing(OONIBError):
    status_code = 400
    log_message = "test-helpers-or-net-test-key-missing"


class TestHelperNotFound(OONIBError):
    status_code = 404
    log_message = "test-helper-not-found"


class InvalidFormatField(OONIBError):
    status_code = 400
    log_message = "invalid-format-field"

class ConfigFileNotSpecified(Exception):
    pass


class ConfigFileDoesNotExist(Exception):
    pass


class InvalidReportDirectory(Exception):
    pass


class InvalidArchiveDirectory(Exception):
    pass


class InvalidInputDirectory(Exception):
    pass


class InvalidDeckDirectory(Exception):
    pass


class InvalidTimestampFormat(Exception):
    pass

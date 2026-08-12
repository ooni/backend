from ooniprobe.routers.v1.probe_services import supports_webconnectivity_lte


def test_supports_webconnectivity_lte():
    # too old
    assert supports_webconnectivity_lte("3.27.9") is False
    assert supports_webconnectivity_lte("2.28.0") is False
    assert supports_webconnectivity_lte("3.27.0-beta.1") is False
    assert supports_webconnectivity_lte("3.9.2") is False

    # new enough
    assert supports_webconnectivity_lte("3.28.0") is True
    assert supports_webconnectivity_lte("3.28.1") is True
    assert supports_webconnectivity_lte("3.29.0") is True
    assert supports_webconnectivity_lte("4.0.0") is True
    assert supports_webconnectivity_lte("3.100.0") is True

    # pre-releases of a supported version already support the experiment
    assert supports_webconnectivity_lte("3.29.0-alpha") is True
    assert supports_webconnectivity_lte("3.28.0-beta.1") is True

    # versions we can't parse are treated as unsupported
    assert supports_webconnectivity_lte("") is False
    assert supports_webconnectivity_lte("unknown") is False
    assert supports_webconnectivity_lte("3.28.x") is False

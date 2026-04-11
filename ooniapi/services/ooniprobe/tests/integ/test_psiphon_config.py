def test_psiphon_config(client):
    resp = client.get("/api/v1/test-list/psiphon-config").json()
    for k in ['ClientPlatform', 'ClientVersion', 'EstablishTunnelTimeoutSeconds',
              'LocalHttpProxyPort', 'LocalSocksProxyPort', 'PropagationChannelId',
              'RemoteServerListDownloadFilename', 'RemoteServerListSignaturePublicKey',
              'RemoteServerListURLs', 'SponsorId', 'TargetApiProtocol', 'UseIndistinguishableTLS']:
        assert k in resp

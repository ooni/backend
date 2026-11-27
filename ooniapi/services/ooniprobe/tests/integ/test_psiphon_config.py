from ooniprobe.common import auth
def test_psiphon_config(client, jwt_encryption_key):
    tok = auth.create_jwt({"registration_time": None, "aud": "probe_token"}, key=jwt_encryption_key)
    resp = client.get("/api/v1/test-list/psiphon-config", headers={"Authorization": f"Bearer {tok}"}).json()
    for k in ['ClientPlatform', 'ClientVersion', 'EstablishTunnelTimeoutSeconds',
              'LocalHttpProxyPort', 'LocalSocksProxyPort', 'PropagationChannelId',
              'RemoteServerListDownloadFilename', 'RemoteServerListSignaturePublicKey',
              'RemoteServerListURLs', 'SponsorId', 'TargetApiProtocol', 'UseIndistinguishableTLS']:
        assert k in resp

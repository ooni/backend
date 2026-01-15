#!/usr/bin/env python3

"""
Use this script to generate a new server state for the anonymous credentials protocol

Two Keys will be generated:

- Secret key: Save it in parameter store as a secret string, do not share it
- Public parameters: A string that will be shared with probes to run the ZKP verification

"""

import ooniauth_py

state = ooniauth_py.ServerState()

secret_key = state.get_secret_key()
public_params = state.get_public_parameters()


print(
    f"""
Secret Key:

    {secret_key}

Public Parameters:

    {public_params}
""")
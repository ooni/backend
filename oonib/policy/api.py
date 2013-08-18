from oonib.policy import handlers

policyAPI = [
    (r"/policy/nettest", handlers.NetTestPolicyHandler),
    (r"/policy/input", handlers.InputPolicyHandler),
]

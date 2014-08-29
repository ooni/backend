from oonib.main import handlers

mainAPI = [
    (r"/.*", handlers.OONIBGlobalHandler)
]

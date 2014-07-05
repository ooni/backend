from cyclone import web

from oonib.main import handlers
from oonib.config import config

mainAPI = [
    (r"/.*", handlers.OONIBGlobalHandler)
]

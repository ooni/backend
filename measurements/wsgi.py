from werkzeug.contrib.fixers import ProxyFix

from measurements.app import create_app

application = create_app()
application.wsgi_app = ProxyFix(application.wsgi_app)

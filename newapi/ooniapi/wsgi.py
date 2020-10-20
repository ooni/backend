
# Entry point for gunicorn, see debian/ooni-api.service

from ooniapi.app import create_app

application = create_app()

#from werkzeug.contrib.fixers import ProxyFix
#application.wsgi_app = ProxyFix(application.wsgi_app)

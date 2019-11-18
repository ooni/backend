# We assume this is going to be running on gunicorn with the gunicorn config
# via gunicorn --config python:measurement.gunicorn_config
from werkzeug.contrib.fixers import ProxyFix

from measurements.app import create_app

from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics

application = create_app()
application.wsgi_app = ProxyFix(application.wsgi_app)

metrics = GunicornPrometheusMetrics(application, group_by="endpoint")

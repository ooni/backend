# We assume this is going to be running on gunicorn with the gunicorn config
# via gunicorn --config python:measurement.gunicorn_config
from werkzeug.contrib.fixers import ProxyFix

from measurements.app import create_app

from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics

app = create_app()
app.wsgi_app = ProxyFix(app.wsgi_app)

metrics = GunicornPrometheusMetrics(app)

from measurements.app import create_app, celery
from measurements.utils import init_celery

app = create_app()
init_celery(app, celery)

from flask import Flask


class App(object):
    def __init__(self, config):
        self._flask_app = Flask("ooni-pipeline")
        self._flask_app.config.update(
            CELERY_BROKER_URL=config.celery.broker_url,
            CELERY_RESULT_BACKEND=config.celery.result_backend
        )
        self.celery = self.make_celery(self._flask_app)

    def make_celery(app):
        from celery import Celery
        celery = Celery(app.import_name,
                        broker=app.config['CELERY_BROKER_URL'])
        celery.conf.update(app.config)
        TaskBase = celery.Task

        class ContextTask(TaskBase):
            abstract = True

            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return TaskBase.__call__(self, *args, **kwargs)

        celery.Task = ContextTask
        return celery

_app = Flask(__name__)

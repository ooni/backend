from datetime import datetime

ISO_TIMESTAMP_SHORT = "%Y%m%dT%H%M%SZ"
OONI_EPOCH = datetime(2012, 12, 5)


def init_celery(app, celery):
    celery.conf.update(app.config)
    celery.conf.update(
        accept_content=["json", "msgpack"],
        result_compression="gzip",
        result_serializer="json",
        task_serializer="json"
    )
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    return celery

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
from datetime import datetime, timedelta

from celery.schedules import crontab
from celery.utils.log import get_task_logger
from flask import current_app

from measurements.app import celery
from measurements.filestore import update_file_metadata
from measurements.utils import OONI_EPOCH

logger = get_task_logger(__name__)


def setup_period_tasks(app):
    if app.config['APP_ENV'] in ['production', 'staging']:
        celery.conf.beat_schedule = {
            'update-files': {
                'task': 'task.update_files',
                'schedule': crontab(minute=0, hour='*/6')
            }
        }


@celery.task(name='task.update_files')
def update_files():
    from measurements.models import ReportFile

    logger.info("Running update files task")

    start_date = OONI_EPOCH
    end_date = datetime.now()

    result = current_app.db_session.query(
        ReportFile.bucket_date
    ).order_by(ReportFile.bucket_date.desc()).first()
    if result is not None:
        start_date = datetime.strptime(result.bucket_date,
                                       "%Y-%m-%d")

    logger.info("Starting from date %s" % start_date)
    while start_date <= end_date:
        target_dir = os.path.join(
            current_app.config['REPORTS_DIR'],
            start_date.strftime("%Y-%m-%d")
        )
        logger.info("Importing files from {}".format(target_dir))
        update_file_metadata(current_app, target_dir, no_check=False)
        start_date += timedelta(days=1)

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
from measurements.utils import OONI_EPOCH

logger = get_task_logger(__name__)


def setup_period_tasks(app):
    if app.config['APP_ENV'] in ['production', 'staging']:
        celery.conf.beat_schedule = {}

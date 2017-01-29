# -*- coding: utf-8 -*-
from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from datetime import datetime, timedelta

dag = DAG(
    dag_id='hist_canning',
    schedule_interval=timedelta(days=1),
    start_date=datetime(2012, 12, 5),
    end_date=datetime(2017, 1, 24), # NB: end_date is included
    default_args={
        'email': 'leon+airflow@darkk.net.ru',
        'retries': 1,
    })

BashOperator(
    pool='datacollector_disk_io',
    task_id='canning',
    bash_command=(
        'sudo --non-interactive /usr/local/bin/docker-trampoline '
        'canning.py "{{ ds }}" "{{ execution_date.isoformat() }}" "{{ (execution_date + dag.schedule_interval).isoformat() }}" '
        '--reports-raw-root /data/ooni/private/reports-raw --canned-root /data/ooni/private/canned'),
    dag=dag)

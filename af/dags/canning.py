# -*- coding: utf-8 -*-
from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from datetime import datetime, timedelta

dag = DAG(
    dag_id='hist_canning',
    schedule_interval=timedelta(days=1),
    start_date=datetime(2012, 12, 5),
    #start_date=datetime(2016, 12, 1),
    end_date=datetime(2017, 2, 20), # NB: end_date is included
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

BashOperator(
    pool='datacollector_disk_io',
    task_id='autoclaving',
    bash_command=(
        'sudo --non-interactive /usr/local/bin/docker-trampoline '
        'autoclaving.py "{{ ds }}" "{{ execution_date.isoformat() }}" "{{ (execution_date + dag.schedule_interval).isoformat() }}" '
        '--canned-root /data/ooni/private/canned --autoclaved-root /data/ooni/public/autoclaved '
        '--bridge-db /data/ooni/private/bridge_db/bridge_db.json'),
    dag=dag)

BashOperator(
    pool='datacollector_disk_io',
    task_id='simhash_text',
    bash_command=(
        'sudo --non-interactive /usr/local/bin/docker-trampoline '
        'centrifugation.py "{{ ds }}" "{{ execution_date.isoformat() }}" "{{ (execution_date + dag.schedule_interval).isoformat() }}" '
        '--autoclaved-root /data/ooni/public/autoclaved --mode simhash-text --simhash-root /data/ooni/public/simhash'),
    dag=dag)

BashOperator(
    pool='datacollector_disk_io',
    task_id='meta_pg',
    bash_command=(
        'sudo --non-interactive /usr/local/bin/docker-trampoline '
        'centrifugation.py "{{ ds }}" "{{ execution_date.isoformat() }}" "{{ (execution_date + dag.schedule_interval).isoformat() }}" '
        '--autoclaved-root /data/ooni/public/autoclaved --mode meta-pg --postgres "host=metadb user=oometa password=d88fOBNIBtVJyBf5ySOokV3J"'),
    dag=dag)

dag.set_dependency('canning', 'autoclaving')
dag.set_dependency('autoclaving', 'simhash_text')
dag.set_dependency('autoclaving', 'meta_pg')

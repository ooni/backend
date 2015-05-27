from __future__ import absolute_import, print_function, unicode_literals

from invoke import Collection, ctask as task


@task
def realtime(ctx):
    print("Starting realtime stream processing")


@task
def upload_reports(ctx, src, dst="s3://ooni-private/reports-raw/yaml/",
                   workers=16, limit=None):
    from pipeline.batch import upload_reports
    upload_reports.run(src_directory=src, dst=dst, worker_processes=workers,
                       limit=limit)

ns = Collection(upload_reports)

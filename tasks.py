from __future__ import absolute_import, print_function, unicode_literals

from invoke import Collection, ctask as task


def _create_luigi_cfg(ctx):
    with open("client.cfg", "w") as fw:
        fw.write("[aws]\n")
        fw.write("access-key-id: %s\n" % ctx.aws.access_key_id)
        fw.write("secret-access-key: %s\n" % ctx.aws.secret_access_key)
        fw.write("[s3]\n")
        fw.write("aws_access_key_id: %s\n" % ctx.aws.access_key_id)
        fw.write("aws_secret_access_key: %s\n" % ctx.aws.secret_access_key)
        fw.write("[kafka]\n")
        fw.write("hosts: %s\n" % ctx.kafka.hosts)


@task
def realtime(ctx):
    print("Starting realtime stream processing")


@task
def upload_reports(ctx, src, dst="s3://ooni-private/reports-raw/yaml/",
                   workers=16, limit=None):
    if limit is not None:
        limit = int(limit)
    from pipeline.batch import upload_reports
    _create_luigi_cfg()
    upload_reports.run(src_directory=src, dst=dst, worker_processes=workers,
                       limit=limit)

ns = Collection(upload_reports)

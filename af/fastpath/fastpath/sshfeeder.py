#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

Feeds measurements from the collectors

"""

from collections import OrderedDict
import datetime
import io
import os
import time
import logging

import paramiko

import warnings

warnings.filterwarnings(action="ignore", module=".*paramiko.*")

import fastpath.normalize as normalize
from fastpath.metrics import setup_metrics

log = logging.getLogger("fastpath")

# See debian/postinst for ssh keygen
ssh_username = "sshfeeder"
pkey_filename_local_path = "ssh/id_ed25519"
pkey_password_file = "/etc/machine-id"
collector_hostnames = ("b.collector.ooni.io", "c.collector.ooni.io")

FIND = "/usr/bin/find {} -maxdepth 1 -type f -cmin -{} -printf '%C@ %s %f\n'"

metrics = setup_metrics(name="fastpath.feeder")

# suppress debug logs
for l in ("paramiko", "paramiko.transport"):
    logging.getLogger(l).setLevel(logging.WARN)


class Source:
    def __init__(self, conf, hostname):
        self._cachedir = conf.sshcachedir
        with open(pkey_password_file) as f:
            pkey_password = f.read().strip()
        pkey_filename = os.path.join(conf.vardir, pkey_filename_local_path)
        pkey = paramiko.Ed25519Key.from_private_key_file(
            pkey_filename, password=pkey_password
        )
        ssh = paramiko.SSHClient()
        ssh.load_host_keys(os.path.join(conf.vardir, "ssh/known_hosts"))
        if conf.devel:
            log.info("SSH TOFU in devel mode!")
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.hostname = hostname
        self.ssh = ssh
        with metrics.timer("connect." + self.hostname):
            ssh.connect(
                hostname,
                username=ssh_username,
                compress=True,
                pkey=pkey,
                look_for_keys=False,
                allow_agent=False,
            )
        self.sftp = ssh.open_sftp()
        # assert self.sftp.get_channel().get_transport()._preferred_compression[1] == 'zlib'
        self.new_downloads = []
        self._archive_dir = f"/data/{self.hostname}/archive"
        self._old_fnames = OrderedDict()
        self._scan_time = None
        self._initial_backlog_minutes = 60 * 6  # too much?

    @metrics.timer("scan")
    def scan_new_files(self):
        """
        Updates self._old_fnames and self._scan_time
        """
        new_fnames = []
        while len(self._old_fnames) > 5000:
            # circular buffer of filenames
            self._old_fnames.pop()

        if self._scan_time is None:  # this is the first run
            backlog_minutes = self._initial_backlog_minutes
        else:
            backlog_minutes = int((time.time() - self._scan_time) / 60) + 1

        self._scan_time = time.time()
        find_cmd = FIND.format(self._archive_dir, backlog_minutes)
        stdin, stdout, stderr = self.ssh.exec_command(find_cmd, timeout=10)
        xc = stdout.channel.recv_exit_status()
        if xc == 0:
            for line in stdout.readlines():
                epoch, size, fn = line.strip().split(" ", 2)
                if not fn.endswith((".json", ".yaml")):
                    continue

                if fn in self._old_fnames:
                    continue

                # creation = datetime.datetime.fromtimestamp(float(epoch))
                new_fnames.append(fn)
                self._old_fnames[fn] = ""
        else:
            log.error(
                "Error running %r on %r as %r", find_cmd, self.hostname, ssh_username
            )
            raise Exception("SSH error")

        if new_fnames:
            # FWIW try to download files in alphabetical order
            new_fnames.sort()
        return new_fnames

    def _fetch_measurement(self, fn):
        """Fetch measurements from one file using a local cache
        :yields: (string of JSON, msmt dict) or (None, msmt dict)
        """
        cfn = self._cachedir / fn
        if cfn.exists():
            metrics.incr("sshcache_hit")
            cfn.touch(exist_ok=True)
            return

        metrics.incr("sshcache_miss")

        try:
            log.debug("Fetching %s", fn)
            fn = os.path.join(self._archive_dir, fn)
            with io.BytesIO() as data:
                metrics.gauge("fetching", 1)
                with metrics.timer("fetch"):
                    self.sftp.getfo(fn, data)
                metrics.gauge("fetching", 0)
                metrics.incr("fetched.count")
                metrics.incr("fetched.data", data.tell())
                data.seek(0)
                if fn.endswith(".yaml"):
                    for msm in normalize.iter_yaml_msmt_normalized(data):
                        yield (None, msm)
                else:
                    # JSON documents
                    while True:
                        line = data.readline()
                        if len(line) == 0:
                            break

                        yield (line, None)

        except Exception as e:
            metrics.gauge("fetching", 0)
            log.exception(e)
            metrics.incr("unhandled_exception")

    def fetch_measurements(self):
        """Fetch new reports
            :yields: (string of JSON, None) or (None, msmt dict)
        """
        new_fnames = self.scan_new_files()
        metrics.incr("new_reports", len(new_fnames))
        for fn in new_fnames:
            for item in self._fetch_measurement(fn):
                yield item


def log_ingestion_delay(msm_jstr, msm):
    try:
        st = msm["measurement_start_time"]
        st = datetime.datetime.strptime(st, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.utcnow()
        s = (now - st).total_seconds()
        if s < 0:
            s = 0
        metrics.gauge("ingestion_delay", s)
    except:
        pass


def feed_measurements_from_collectors(conf, start_time=None):
    """Fetch reports from collectors
    Yields measurements one by one as:
    :yields: (string of JSON, None) or (None, msmt dict)
    """
    # Connect to all collectors here
    sources = [Source(conf, hn) for hn in collector_hostnames]
    stop_after = conf.stop_after
    if stop_after == 0:
        return
    while True:
        throttle = True
        for source in sources:
            log.debug("Checking %s", source.hostname)
            for i in source.fetch_measurements():
                if not i:
                    break

                log_ingestion_delay(*i)
                yield i
                throttle = False
                if stop_after is not None:
                    stop_after -= 1
                    if stop_after == 0:
                        log.debug("Stopping due to stop_after")
                        return

        # sleep only if no reports were fetched
        if throttle:
            time.sleep(1)

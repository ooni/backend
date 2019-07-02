#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import re

RE_LOG_LINE = re.compile(
    r"^(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (?P<day>[0123]\d) (?P<hour>[0-2]\d):(?P<min>[0-5]\d):(?P<sec>[0-5]\d)\.[0-9]{3} (?P<msg>.*)$"
)

# ignore some log lines that provide no useful information
MSG_IGNORE = {
    "[notice] Catching signal TERM, exiting cleanly.",
    '[notice] Configuration file "/dev/null/non-existant-on-purpose" not present, using reasonable defaults.',
    '[notice] Configuration file "/non-existant" not present, using reasonable defaults.',
    "[notice] New control connection opened from 127.0.0.1.",
    "[notice] Tor can't help you if you use it wrong! Learn how to be safe at https://www.torproject.org/download/download#warning",
    "[notice] Tor has successfully opened a circuit. Looks like client functionality is working.",  # just a prev message to 100%
    "[warn] You are running Tor as root. You don't need to, and you probably shouldn't.",  # user privacy?
}
MSG_RE_IGNORE = map(
    re.compile,
    (
        r"^\[notice\] Opening (?:Control|Socks) listener on 127\.0\.0\.1:\d+$",
        r"^\[notice\] Parsing GEOIP (?:IPv[46] )file /.*\.$",
        r"^\[notice\] Tor [^ ]+ (?:\(git-[^ ]+\) )?opening (?:new )?log file.$",  # nice ver: `0.3.0.1-alpha-dev (git-f4ebbf756787d49a+5156f73)`
    ),
)

# convert well-known bootstrap stages to easy-to-parse messages
MSG_BOOTSTRAP = {
    "[notice] Bootstrapped 0%: Starting": 0,
    "[notice] Bootstrapped 5%: Connecting to directory server": 5,
    "[notice] Bootstrapped 10%: Finishing handshake with directory server": 10,
    "[notice] Bootstrapped 15%: Establishing an encrypted directory connection": 15,
    "[notice] Bootstrapped 20%: Asking for networkstatus consensus": 20,
    "[notice] Bootstrapped 25%: Loading networkstatus consensus": 25,
    "[notice] Bootstrapped 40%: Loading authority key certs": 40,
    "[notice] Bootstrapped 45%: Asking for relay descriptors": 45,
    "[notice] Bootstrapped 80%: Connecting to the Tor network": 80,
    "[notice] Bootstrapped 85%: Finishing handshake with first hop": 85,
    "[notice] Bootstrapped 90%: Establishing a Tor circuit": 90,
    "[notice] Bootstrapped 100%: Done": 100,
}
for _ in xrange(50, 80):
    MSG_BOOTSTRAP["[notice] Bootstrapped {}%: Loading relay descriptors".format(_)] = _
for _ in MSG_BOOTSTRAP.keys():
    MSG_BOOTSTRAP[_ + "."] = MSG_BOOTSTRAP[_]  # some tor versions have dots, some don't


def parse_tor_log(tor_log):
    """ The purpose is to convert absolute timestamps into relative (parsing is
        PITA) and to handle common messages (either ignore them or convert into
        Bootstrapped percent).
    """
    tor_log = tor_log.rstrip("\n").split("\n")

    # 24h boundary? Leap year? Daylight-saving time? Leap second? WELCOME TO HELL!
    base_date, base_ts = None, None

    ret = []
    for line in tor_log:
        m = RE_LOG_LINE.match(line)
        if m is None:
            ret.append({"!": line})  # Bad tor_log line
            continue
        m = m.groupdict()
        date = (m["mon"], int(m["day"]))
        ts = int(m["hour"]) * 3600 + int(m["min"]) * 60 + int(m["sec"])
        msg = m["msg"]

        if base_date is None:
            base_date, base_ts = date, ts

        if msg in MSG_IGNORE or any(r.match(msg) for r in MSG_RE_IGNORE):
            continue

        if date == base_date:
            ts = ts - base_ts
        elif date[1] == base_date[1] + 1 or date[1] == 1:
            ts = ts - base_ts + 86400
        else:
            raise RuntimeError("tor_log spans over two+ days", base_date, date)
        # Time _should_ never go back, but, of course, it does (sometimes).

        if msg in MSG_BOOTSTRAP:
            ret.append({"t": ts, "%": MSG_BOOTSTRAP[msg]})
        else:
            ret.append({"t": ts, "_": msg})
    return ret


if __name__ == "__main__":

    def main():
        # for f in ????-??-??/vanilla_tor*.tar.lz4; do tar -I lz4 -x --to-stdout -f $f; done | jq -c .test_keys.tor_log | python tor_log.py
        import sys, json

        for line in sys.stdin:
            tor_log = json.loads(line)
            if tor_log is not None:
                tor_log = parse_tor_log(tor_log)
                json.dump(tor_log, sys.stdout)
                sys.stdout.write("\n")

    main()

#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import numbers
import os
import re
from cStringIO import StringIO

import psycopg2


class PGCopyFrom(object):
    # Write buffer for COPY command to be able to COPY to several
    # output tables over single postgres session. Alternative is to use several
    # sessions and pipe data across threads with significant CPU overhead and
    # inability to process every OONI measurement using set of functions to
    # have clean "residual" document after data extraction.
    def __init__(
        self, pgconn, table, badsink=None, badrow_fmt=None, wbufsize=2097152, **kwargs
    ):
        # default chunk size is taken as approx. cwnd between production VMs
        self.__pgconn = pgconn
        self.__table = table
        self.__badsink = badsink
        self.__badrow_fmt = (
            badrow_fmt
        )  # callback(table_name, copy_from_row_text_for_table) -> copy_from_row_text_for_badsink
        self.flush = (
            self.__flush_easygoing if badsink is None else self.__flush_stubborn
        )
        self.__wbufsize = wbufsize
        self.__kwargs = kwargs
        self.__buf = StringIO()

    def write(self, line):
        assert len(line) == 0 or line[-1] == "\n"
        pos = self.__buf.tell()
        if pos > 0 and pos + len(line) > self.__wbufsize:
            self.flush()
        self.__buf.write(line)

    def __flush_easygoing(self):
        self.__buf.reset()
        with self.__pgconn.cursor() as c:
            c.copy_from(self.__buf, self.__table, **self.__kwargs)
        self.__buf.reset()
        self.__buf.truncate()

    def __flush_stubborn(self):
        self.__buf.seek(0, os.SEEK_END)
        buf_size = self.__buf.tell()
        bad_lines = []
        base_line = 0
        start_pos = 0
        bad_size = 0
        good_size = 0
        eols = None
        with self.__pgconn.cursor() as c:
            while start_pos < buf_size:
                self.__buf.seek(start_pos)
                c.execute("SAVEPOINT flush_stubborn")
                try:
                    c.copy_from(self.__buf, self.__table, **self.__kwargs)
                except (psycopg2.DataError, psycopg2.IntegrityError) as exc:
                    m = re.search(
                        r"\bCOPY {}, line (\d+)".format(self.__table), exc.diag.context
                    )
                    if (
                        m is not None
                    ):  # yes, it's best possible way to extract that datum :-(
                        line = int(m.group(1)) - 1
                        assert line >= 0
                        line += base_line
                        c.execute("ROLLBACK TO SAVEPOINT flush_stubborn")
                    else:
                        raise
                else:
                    line = None
                c.execute(
                    "RELEASE SAVEPOINT flush_stubborn"
                )  # NB: ROLLBACK does not RELEASE, https://www.postgresql.org/message-id/1354145331.1766.84.camel%40sussancws0025
                if line is None:
                    self.__buf.truncate(start_pos)
                    good_size += buf_size - start_pos
                    start_pos = buf_size  # to break the loop
                else:
                    if eols is None:  # delay computation till error
                        eols = list(
                            m.end() for m in re.finditer("\n", self.__buf.getvalue())
                        )
                    start = eols[line - 1] if line > 0 else 0
                    end = eols[line]
                    if bad_lines and bad_lines[-1][1] == start:
                        start, _ = bad_lines.pop()  # merge consequent bad lines
                    bad_lines.append((start, end))
                    assert end > start_pos
                    start_pos = end
                    base_line = line + 1
            # __buf is either empty or ends with some bad lines now
            if bad_lines:
                for start, end in bad_lines:
                    self.__buf.seek(start)
                    bad = self.__buf.read(end - start)
                    assert len(bad) == end - start
                    self.__badsink.write(self.__badrow_fmt(self.__table, bad))
                    bad_size += len(bad)
                good_buf = StringIO()
                # transforming bad_lines to good_lines
                good_lines = list(sum(bad_lines, ()))
                if good_lines[0] == 0:  # first blob was bad
                    good_lines.pop(0)
                else:  # first blob was good
                    good_lines.insert(0, 0)
                good_lines.pop()  # last blob is always bad :)
                for start, end in zip(good_lines[::2], good_lines[1::2]):
                    self.__buf.seek(start)
                    good_buf.write(self.__buf.read(end - start))
                good_size += good_buf.tell()
                if good_buf.tell():
                    self.__buf = good_buf
                    self.__flush_easygoing()
                else:
                    self.__buf.truncate(0)
            assert good_size + bad_size == buf_size
        assert self.__buf.tell() == 0

    def close(self):
        self.flush()
        self.__buf.close()

    @property
    def closed(self):
        return self.__buf.closed


BAD_UTF8_RE = re.compile(  # https://stackoverflow.com/questions/18673213/detect-remove-unpaired-surrogate-character-in-python-2-gtk
    ur"""(?x)            # verbose expression (allows comments)
    (                    # begin group
    [\ud800-\udbff]      #   match leading surrogate
    (?![\udc00-\udfff])  #   but only if not followed by trailing surrogate
    )                    # end group
    |                    #  OR
    (                    # begin group
    (?<![\ud800-\udbff]) #   if not preceded by leading surrogate
    [\udc00-\udfff]      #   match trailing surrogate
    )                    # end group
    |                    #  OR
    \u0000
    """
)

PG_ARRAY_SPECIAL_RE = re.compile('[\t\x0a\x0b\x0c\x0d {},"\\\\]')


def pg_quote(s):
    # The following characters must be preceded by a backslash if they
    # appear as part of a column value: backslash itself, newline, carriage
    # return, and the current delimiter character.
    # -- https://www.postgresql.org/docs/9.6/static/sql-copy.html
    if isinstance(s, basestring):
        # postgres requires UTF8, it's also unhappy about
        # - unpaired surrogates https://www.postgresql.org/message-id/20060526134833.GC27513%40svana.org
        #   example at 2016-04-01/http_requests.06.tar.lz4 | grep myfiona.co.kr
        # - \u0000 as in ``DETAIL:  \u0000 cannot be converted to text.``
        #   example at https://github.com/TheTorProject/ooni-pipeline/issues/65
        if isinstance(s, str):
            s = unicode(s, "utf-8")
        s = BAD_UTF8_RE.sub(u"\ufffd", s).encode("utf-8")
        return (
            s.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
    elif s is None:
        return "\\N"
    elif isinstance(s, bool):  # WTF: assert isinstance(True, numbers.Number)!
        return "TRUE" if s else "FALSE"
    elif isinstance(s, numbers.Number):
        return s
    elif isinstance(s, list):
        if all(isinstance(el, basestring) for el in s):
            escaped = []
            for el in s:
                if PG_ARRAY_SPECIAL_RE.search(el):
                    escaped.append(
                        '"' + el.replace("\\", "\\\\").replace('"', '\\"') + '"'
                    )  # 8-[ ~ ]
                else:
                    escaped.append(el)
            return pg_quote("{" + ",".join(escaped) + "}")  # yes, once more!
        elif all(isinstance(el, numbers.Number) for el in s):
            return "{" + ",".join(map(str, s)) + "}"
        else:
            raise RuntimeError("Unable to quote list of unknown type", s)
    else:
        raise RuntimeError("Unable to quote unknown type", s)


def _pg_unquote(s):  # is used only in the test
    if not isinstance(s, basestring):
        raise RuntimeError("Unable to quote unknown type", s)
    if s != "\\N":
        return s.decode("string_escape")  # XXX: gone in Python3
    else:
        return None


def pg_binquote(s):
    assert isinstance(s, str)
    return "\\\\x" + s.encode("hex")


def pg_uniquote(s):
    if isinstance(s, str):
        s = unicode(s, "utf-8")
    assert isinstance(s, unicode)
    return BAD_UTF8_RE.sub(
        u"\ufffd", s
    )  # `re` is smart enough to return same object in case of no-op

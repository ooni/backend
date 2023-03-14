"""
ASN Meta - basic functional testing
"""

import datetime

from unittest.mock import Mock, MagicMock, create_autospec, call

import pytest

from analysis import asnmeta_updater


def test_asnmeta_updater():
    asnmeta_updater.Clickhouse = create_autospec(asnmeta_updater.Clickhouse)
    asnmeta_updater.metrics = Mock()

    mock_client = MagicMock()
    asnmeta_updater.Clickhouse.from_url.return_value = mock_client
    def mocked_execute(q, data=None, **kw):
        if q == "SELECT count() FROM asnmeta_tmp":
            return [[250_000]]

        if q.startswith("INSERT INTO asnmeta"):
            assert len(data) > 250_000

        return [[]]
    mock_client.execute.side_effect = mocked_execute

    conf = Mock()
    conf.dry_run = False

    asnmeta_updater.update_asnmeta(conf)
    assert len(mock_client.execute.call_args_list) == 6

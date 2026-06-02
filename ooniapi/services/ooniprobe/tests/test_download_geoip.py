from datetime import datetime, timezone
from pathlib import Path

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from ooniprobe.download_geoip import (
    geoip_release_url,
    try_update,
)

FROZEN_NOW = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)


def _availability(current: bool, last_month: bool):
    last_month_date = FROZEN_NOW - relativedelta(months=1)
    current_url = geoip_release_url(FROZEN_NOW)[2]
    last_month_url = geoip_release_url(last_month_date)[2]

    def _is_latest_available(url: str) -> bool:
        if url == current_url:
            return current
        if url == last_month_url:
            return last_month
        return False

    return _is_latest_available


def _patch_is_latest_available(monkeypatch, current: bool, last_month: bool):
    monkeypatch.setattr(
        "ooniprobe.download_geoip.is_latest_available",
        _availability(current, last_month),
    )


def _patch_download_geoip(monkeypatch, urls: set[str]):
    def _fake_download(db_dir: Path, url: str, filename: str) -> None:
        assert url in urls
        db_dir.mkdir(parents=True, exist_ok=True)
        (db_dir / filename).touch()

    monkeypatch.setattr("ooniprobe.download_geoip.download_geoip", _fake_download)


@freeze_time(FROZEN_NOW)
def test_old_present_new_available(
    monkeypatch,
    download_geoip_db_dir,
    last_month_geoip_db,
):
    current_url = geoip_release_url(FROZEN_NOW)[2]
    _patch_download_geoip(monkeypatch, {current_url})
    _patch_is_latest_available(monkeypatch, current=True, last_month=False)

    result = try_update(str(download_geoip_db_dir))

    assert result == download_geoip_db_dir / "asn_cc.mmdb"
    assert (download_geoip_db_dir / "asn_cc.mmdb").exists()
    assert (download_geoip_db_dir / "geoipdbts").exists()


@freeze_time(FROZEN_NOW)
def test_old_not_present_new_unavailable(
    monkeypatch,
    download_geoip_db_dir,
):
    last_month = FROZEN_NOW - relativedelta(months=1)
    last_month_url = geoip_release_url(last_month)[2]
    _patch_download_geoip(monkeypatch, {last_month_url})
    _patch_is_latest_available(monkeypatch, current=False, last_month=True)

    result = try_update(str(download_geoip_db_dir))

    assert result == download_geoip_db_dir / "asn_cc.mmdb"
    assert (download_geoip_db_dir / "asn_cc.mmdb").exists()
    assert (download_geoip_db_dir / "geoipdbts").exists()


@freeze_time(FROZEN_NOW)
def test_download_nothing_no_db(
    monkeypatch,
    download_geoip_db_dir,
):
    _patch_is_latest_available(monkeypatch, current=False, last_month=False)

    result = try_update(str(download_geoip_db_dir))

    assert result is None
    assert not (download_geoip_db_dir / "asn_cc.mmdb").exists()
    assert not (download_geoip_db_dir / "geoipdbts").exists()

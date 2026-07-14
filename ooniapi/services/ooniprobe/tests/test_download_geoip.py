from tests.conftest import GEOIP_FROZEN_TIME
from pathlib import Path

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from ooniprobe.download_geoip import (
    geoip_release_url,
    try_update,
)



def _current_month_ts() -> str:
    return geoip_release_url(GEOIP_FROZEN_TIME)[0]


def _last_month_ts() -> str:
    return geoip_release_url(GEOIP_FROZEN_TIME- relativedelta(months=1))[0]


def _geoipdbts(db_dir: Path) -> str:
    return (db_dir / "geoipdbts").read_text()


def _availability(current: bool, last_month: bool):
    last_month_date = GEOIP_FROZEN_TIME - relativedelta(months=1)
    current_url = geoip_release_url(GEOIP_FROZEN_TIME)[2]
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


def _patch_download_geoip(monkeypatch):
    def _fake_download(db_dir: Path, url: str, filename: str) -> None:
        db_dir.mkdir(parents=True, exist_ok=True)
        (db_dir / filename).touch()

    monkeypatch.setattr("ooniprobe.download_geoip.download_geoip", _fake_download)


@freeze_time(GEOIP_FROZEN_TIME)
def test_old_present_new_available(
    monkeypatch,
    download_geoip_db_dir,
    last_month_geoip_db,
):
    _patch_download_geoip(monkeypatch)
    _patch_is_latest_available(monkeypatch, current=True, last_month=False)

    db_path, downloaded = try_update(str(download_geoip_db_dir))

    assert downloaded is True
    assert db_path == download_geoip_db_dir / "asn_cc.mmdb"
    assert (download_geoip_db_dir / "asn_cc.mmdb").exists()
    assert _geoipdbts(download_geoip_db_dir) == _current_month_ts()


@freeze_time(GEOIP_FROZEN_TIME)
def test_old_not_present_new_unavailable(
    monkeypatch,
    download_geoip_db_dir,
):
    _patch_download_geoip(monkeypatch)
    _patch_is_latest_available(monkeypatch, current=False, last_month=True)

    db_path, downloaded = try_update(str(download_geoip_db_dir))

    assert downloaded is True
    assert db_path == download_geoip_db_dir / "asn_cc.mmdb"
    assert (download_geoip_db_dir / "asn_cc.mmdb").exists()
    assert _geoipdbts(download_geoip_db_dir) == _last_month_ts()


@freeze_time(GEOIP_FROZEN_TIME)
def test_old_present_new_unavailable(
    monkeypatch,
    download_geoip_db_dir,
    last_month_geoip_db,
):
    monkeypatch.setattr(
        "ooniprobe.download_geoip.has_valid_geoip_db",
        lambda db_dir: (db_dir / "asn_cc.mmdb").exists(),
    )
    _patch_is_latest_available(monkeypatch, current=False, last_month=False)

    db_path, downloaded = try_update(str(download_geoip_db_dir))

    assert downloaded is False
    assert db_path == download_geoip_db_dir / "asn_cc.mmdb"
    assert _geoipdbts(download_geoip_db_dir) == _last_month_ts()


@freeze_time(GEOIP_FROZEN_TIME)
def test_already_updated_current_month(
    monkeypatch,
    download_geoip_db_dir,
    current_month_geoip_db,
):
    monkeypatch.setattr(
        "ooniprobe.download_geoip.has_valid_geoip_db",
        lambda db_dir: (db_dir / "asn_cc.mmdb").exists(),
    )
    db_path, downloaded = try_update(str(download_geoip_db_dir))

    assert downloaded is False
    assert db_path == download_geoip_db_dir / "asn_cc.mmdb"
    assert _geoipdbts(download_geoip_db_dir) == _current_month_ts()


@freeze_time(GEOIP_FROZEN_TIME)
def test_download_nothing_no_db(
    monkeypatch,
    download_geoip_db_dir,
):
    _patch_is_latest_available(monkeypatch, current=False, last_month=False)

    db_path, downloaded = try_update(str(download_geoip_db_dir))

    assert downloaded is False
    assert db_path is None
    assert not (download_geoip_db_dir / "asn_cc.mmdb").exists()
    assert not (download_geoip_db_dir / "geoipdbts").exists()

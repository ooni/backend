from .utils import getj
import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_profiling_enabled(client, db, tmp_path, profiling_enabled):
    report_path: Path = tmp_path / "report.html"

    assert not report_path.exists()

    getj(client, "/api/v1/manifest")

    assert report_path.exists()

@pytest.mark.asyncio
async def test_profiling_disabled(client, db, tmp_path, profiling_disabled):
    report_path: Path = tmp_path / "report.html"

    assert not report_path.exists()

    getj(client, "/api/v1/manifest")

    assert not report_path.exists()

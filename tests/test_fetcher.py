import json
import os
import time

import httpx2 as httpx
import pytest

import fetcher

SAMPLE_HTML = """
<script>
var MPT = {
  20261019: "144805070555061507211233130015291545180418091924194512301315"
};
</script>
"""


def test_get_mpt_schedule_hit_fresh(tmp_path, monkeypatch):
    """Serves directly from cache without hitting upstream if < 24h old."""
    cache_file = tmp_path / "mpt_cache.json"
    cache_file.write_text(json.dumps({"20261019": "144805070555061507211233130015291545180418091924194512301315"}))
    monkeypatch.setattr(fetcher, "CACHE_FILE", cache_file)

    # If upstream is called, fail the test immediately
    monkeypatch.setattr(fetcher, "fetch_upstream_html", lambda: pytest.fail("Should not call upstream on fresh cache"))

    data, status = fetcher.get_mpt_schedule("20261019")
    assert status == "HIT_FRESH"
    assert "20261019" in data


def test_get_mpt_schedule_refreshes_upstream_on_cold_cache(tmp_path, monkeypatch):
    """Scrapes upstream and writes to disk when cache doesn't exist."""
    cache_file = tmp_path / "mpt_cache.json"
    monkeypatch.setattr(fetcher, "CACHE_FILE", cache_file)
    monkeypatch.setattr(fetcher, "fetch_upstream_html", lambda: SAMPLE_HTML)

    _data, status = fetcher.get_mpt_schedule("20261019")
    assert status == "REFRESHED_UPSTREAM"
    assert cache_file.exists()
    assert fetcher.CACHE_DEGRADED_MODE._value.get() == 0.0


def test_get_mpt_schedule_degraded_fallback_when_upstream_fails(tmp_path, monkeypatch):
    """Falls back to stale (>24h old) cache when upstream is down."""
    cache_file = tmp_path / "mpt_cache.json"
    cache_file.write_text(json.dumps({"20261019": "144805070555061507211233130015291545180418091924194512301315"}))
    
    # Age the file modification time to 30 hours ago so it misses HIT_FRESH
    old_time = time.time() - (30 * 3600)
    os.utime(cache_file, (old_time, old_time))

    monkeypatch.setattr(fetcher, "CACHE_FILE", cache_file)

    def mock_fail():
        raise httpx.ConnectTimeout("Upstream timeout")

    monkeypatch.setattr(fetcher, "fetch_upstream_html", mock_fail)

    data, status = fetcher.get_mpt_schedule("20261019")
    assert status == "DEGRADED_CACHE_FALLBACK"
    assert "20261019" in data
    assert fetcher.CACHE_DEGRADED_MODE._value.get() == 1.0


def test_get_mpt_schedule_total_outage_raises_runtime_error(tmp_path, monkeypatch):
    """Raises RuntimeError when upstream fails AND no local cache exists."""
    cache_file = tmp_path / "nonexistent.json"
    monkeypatch.setattr(fetcher, "CACHE_FILE", cache_file)
    monkeypatch.setattr(fetcher, "fetch_upstream_html", lambda: (_ for _ in ()).throw(httpx.ConnectError("Down")))

    with pytest.raises(RuntimeError, match="Upstream down and no local cache available"):
        fetcher.get_mpt_schedule("20261019")


def test_corrupt_cache_self_heals_from_upstream(tmp_path, monkeypatch):
    """Logs warning on corrupt JSON cache and heals by fetching upstream."""
    cache_file = tmp_path / "mpt_cache.json"
    cache_file.write_text("{corrupt-json-garbage")
    monkeypatch.setattr(fetcher, "CACHE_FILE", cache_file)
    monkeypatch.setattr(fetcher, "fetch_upstream_html", lambda: SAMPLE_HTML)

    _data, status = fetcher.get_mpt_schedule("20261019")
    assert status == "REFRESHED_UPSTREAM"
    assert json.loads(cache_file.read_text())["20261019"].startswith("1448")
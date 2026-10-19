from datetime import datetime

from fastapi.testclient import TestClient

import main
from parser import TZ

client = TestClient(main.app)

RAW_60 = "144805070555061507211233130015291545180418091924194512301315"


def test_healthz_endpoint(tmp_path, monkeypatch):
    cache_file = tmp_path / "mpt_cache.json"
    cache_file.write_text("{}")
    monkeypatch.setattr(main, "CACHE_FILE", cache_file)

    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "cache_exists": True,
        "timezone": "America/Toronto",
    }


def test_metrics_endpoint_exposes_prometheus_slis():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "mosque_upstream_fetch_total" in resp.text
    assert "mosque_cache_degraded_mode" in resp.text


def test_get_today_schedule_200_ok(monkeypatch):
    today_key = datetime.now(TZ).strftime("%Y%m%d")
    monkeypatch.setattr(
        main,
        "get_mpt_schedule",
        lambda target_date, force_refresh=False: ({today_key: RAW_60}, "HIT_FRESH"),
    )

    resp = client.get("/api/v1/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == today_key
    assert body["cache_status"] == "HIT_FRESH"
    assert "fajr_azan" in body


def test_get_today_schedule_503_on_upstream_and_cache_failure(monkeypatch):
    def mock_outage(target_date, force_refresh=False):
        raise RuntimeError("Upstream down and no local cache available")

    monkeypatch.setattr(main, "get_mpt_schedule", mock_outage)

    resp = client.get("/api/v1/today")
    assert resp.status_code == 503
    assert "Upstream down" in resp.json()["detail"]


def test_get_today_schedule_503_when_today_key_missing_from_payload(monkeypatch):
    """If cache is >72h old and doesn't contain today's key, return 503."""
    monkeypatch.setattr(
        main,
        "get_mpt_schedule",
        lambda target_date, force_refresh=False: ({"19990101": RAW_60}, "DEGRADED_CACHE_FALLBACK"),
    )

    resp = client.get("/api/v1/today")
    assert resp.status_code == 503
    assert "missing from upstream and 72h cache" in resp.json()["detail"]
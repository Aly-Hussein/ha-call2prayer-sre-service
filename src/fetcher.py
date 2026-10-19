import json
import logging
import os
import time
from pathlib import Path

import httpx2 as httpx
from prometheus_client import Counter, Gauge, Histogram
from tenacity import retry, stop_after_attempt, wait_exponential

from parser import extract_mpt_dict

logger = logging.getLogger("mosque-sre")

CACHE_FILE = Path(os.getenv("CACHE_FILE_PATH", "/data/mpt_cache.json"))
MOSQUE_URL = os.getenv("MOSQUE_URL", "https://mosqueprayertimes.com/alsalam-mtl")

# Prometheus SLIs
UPSTREAM_FETCH_TOTAL = Counter(
    "mosque_upstream_fetch_total",
    "Total upstream HTTP fetch attempts to mosqueprayertimes.com",
    ["status"],
)
UPSTREAM_LATENCY = Histogram(
    "mosque_upstream_latency_seconds",
    "Latency of upstream HTML scrape",
)
CACHE_DEGRADED_MODE = Gauge(
    "mosque_cache_degraded_mode",
    "1 if currently serving from fallback local cache due to upstream error, 0 otherwise",
)
CACHE_LAST_UPDATED = Gauge(
    "mosque_cache_last_updated_timestamp_seconds",
    "Unix timestamp of the last successful cache write",
)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def fetch_upstream_html() -> str:
    with UPSTREAM_LATENCY.time(), httpx.Client(
        timeout=10.0,
        headers={"User-Agent": "Homelab-SRE-Monitor/1.0 (+https://github.com/aly)"},
    ) as client:
        resp = client.get(MOSQUE_URL)
        resp.raise_for_status()
        return resp.text


def get_mpt_schedule(target_date: str, force_refresh: bool = False) -> tuple[dict[str, str], str]:
    """
    Returns (mpt_dict, cache_status).
    Avoids hammering upstream if target_date is already fresh in today's cache unless forced.
    """
    if not force_refresh and CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text())
            # If cache was updated within 24 hrs and has target_date, serve immediately
            mtime_age = time.time() - CACHE_FILE.stat().st_mtime
            if target_date in cached and mtime_age < 86400:  # 24 hours fresh
                return cached, "HIT_FRESH"
        except Exception as e: # noqa: BLE001
            logger.warning("Corrupt cache file detected, forcing upstream fetch: %s", e)

    try:
        html = fetch_upstream_html()
        mpt_data = extract_mpt_dict(html)
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(mpt_data, indent=2))
        
        UPSTREAM_FETCH_TOTAL.labels(status="success").inc()
        CACHE_DEGRADED_MODE.set(0)
        CACHE_LAST_UPDATED.set(time.time())
        logger.info("Successfully refreshed MPT cache with keys: %s", list(mpt_data.keys()))
        return mpt_data, "REFRESHED_UPSTREAM"
    except Exception as e:
        UPSTREAM_FETCH_TOTAL.labels(status="error").inc()
        CACHE_DEGRADED_MODE.set(1)
        logger.warning("Upstream fetch failed (%s). Falling back to 72h local cache.", e)
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text()), "DEGRADED_CACHE_FALLBACK"
        raise RuntimeError("Upstream down and no local cache available") from e
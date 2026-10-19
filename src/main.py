import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from fetcher import CACHE_FILE, get_mpt_schedule
from parser import TZ, parse_day_string

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mosque-sre")

app = FastAPI(
    title="Call2Prayer SRE Service",
    version="1.0.0",
)


@app.get("/healthz")
def healthcheck():
    cache_exists = CACHE_FILE.exists()
    return {
        "status": "ok",
        "cache_exists": cache_exists,
        "timezone": str(TZ),
    }


@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/today")
def get_today_schedule(refresh: bool = Query(default=False, description="Force upstream scrape")):
    today_key = datetime.now(TZ).strftime("%Y%m%d")
    try:
        mpt_data, cache_status = get_mpt_schedule(today_key, force_refresh=refresh)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if today_key not in mpt_data:
        raise HTTPException(
            status_code=503,
            detail=f"Schedule for {today_key} missing from upstream and 72h cache",
        )

    schedule = parse_day_string(today_key, mpt_data[today_key], cache_status=cache_status)
    return schedule.to_dict()
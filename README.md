# Call2Prayer SRE Microservice & Home Assistant Package

[![CI & Upstream Contract Check](https://img.shields.io/badge/build-passing-brightgreen.svg)](#ci-cd--contract-testing)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-00a393.svg)](https://fastapi.tiangolo.com/)
[![Prometheus](https://img.shields.io/badge/Metrics-Prometheus-e6522c.svg)](https://prometheus.io/)
[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-orange.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0)

A fault-tolerant, containerized Python microservice and modular Home Assistant package that ingests daily prayer and Iqama schedules from [As-Salam Mosque (Montreal)](https://mosqueprayertimes.com/alsalam-mtl), exposes Prometheus observability metrics, and drives automated Azan and pre-Iqama smart speaker broadcasts with **zero dependency on cloud APIs at runtime**.

---

## 1. Overview

Most smart-home prayer integrations and azan apps on phones rely on astronomical calculation formulas. While useful for general prayer windows, they cannot know a local mosque's actual **Iqama** (congregation) schedule. Furthermore, scraping web tables directly inside Home Assistant using inline regex templates is brittle and fails silently if the upstream website or home internet goes down overnight.

**Call2Prayer** solves this by decoupling schedule ingestion into a resilient local microservice:
* **Lightweight Parsing (~25MB RAM):** Extracts the raw 60-character schedule dictionary (`MPT`) directly from the upstream HTML source, avoiding the need for a heavy headless browser (Selenium/Playwright).
* **72-Hour Offline Cache Fallback:** Because the upstream payload includes a 4-day rolling window, every successful fetch is cached to disk (`/data/mpt_cache.json`). If your ISP or the mosque website is unreachable during the `00:03:00` daily sync, the API falls back to the local cache so your Fajr and Iqama automations still fire on time.
* **Drop-In Home Assistant Package:** Hydrates **14 native entities** (`device_class: timestamp`) in a single daily HTTP poll, driving automated Azan broadcasts and `-15 minute` pre-Iqama reminders on smart speakers.
---

## 2. System Architecture & UML Diagrams

### Zero-Trust Deployment & Firewall Topology

```text
[ mosqueprayertimes.com ] 
        ▲
        │ HTTPS GET (Daily @ 00:03 + Exponential Backoff)
        │
┌───────┴───────────────────────────────────────────────────────────────────────────┐
│ PROXMOX VE HYPERVISOR (Default Firewall: DROP | Admin SSH Key-Only)               │
│                                                                                   │
│  ┌─────────────────────────────────────────┐      ┌────────────────────────────┐  │
│  │     LXC  : Unprivileged Docker Host     │      │ VM : Home Assistant OS     │  │
│  │  ┌───────────────────────────────────┐  │      │  ┌──────────────────────┐  │  │
│  │  │ ha-mosque-sre-service (:8000)     │◄─┼──────┼──┤ call2prayer.yaml     │  │  │
│  │  │ - FastAPI + Uvicorn (UID 10001)   │  │ HTTP │  │ - 14x REST Sensors   │  │  │
│  │  │ - Read-Only RootFS, Cap-Drop ALL  │  │ Poll │  │ - 00:03 & Boot Sync  │  │  │
│  │  │ - Prometheus /metrics & /healthz  │  │      │  │ - Azan/Iqama Scripts │  │  │
│  │  │                                   │  │      │  └──────────────────────┘  │  │
│  │  └─────────────────┬─────────────────┘  │      └──────────────┬─────────────┘  │
│  │                    │ Read/Write         │                     │                │
│  │                    ▼                    │                     │ LAN Cast       │
│  │         [ /data/mpt_cache.json ]        │                     ▼                │
│  │          (72-Hour Local Fallback)       │        [ Google Nest Speaker ]       │
│  └─────────────────────────────────────────┘                                      │
└───────────────────────────────────────────────────────────────────────────────────┘
```

* **Deployment Diagram:** See [`docs/deployment_diagram.md`](docs/deployment_diagram.png) for the complete Proxmox VE, LXC firewall, and container isolation topology.
* **Resilience Sequence Diagram:** See [`docs/sequence_diagram_resilience.md`](docs/sequence_diagram_resilience.png) for the retry, cache-fallback, and hardware trigger lifecycle.
* **CI/CD & Contract Pipeline:** See [`docs/cicd_activity_diagram.md`](docs/cicd_activity.png) for the automated test and upstream drift detection workflow.

---

## 3. Service Level Indicators (SLIs) & Objectives (SLOs)

| Category | Service Level Indicator (SLI) | Objective (SLO) | Engineering Mitigation |
| :--- | :--- | :--- | :--- |
| **Availability** | Proportion of successful `HTTP 200` responses from `/api/v1/today` | **99.9%** (30d window) | Local 72-hour rolling disk cache (`mpt_cache.json`) decouples local API availability from WAN/upstream outages. |
| **Latency** | `p99` API response time | **< 50ms** (Cache Hit)<br>**< 2500ms** (Cache Miss) | Served directly from local state if hydrated within the last 24 hours (`HIT_FRESH`), bypassing synchronous upstream network I/O. |
| **Freshness** | Time elapsed since last successful upstream cache write | **< 24 hours** (Target)<br>**< 72 hours** (Hard Limit) | Monitored via `mosque_cache_last_updated_timestamp_seconds` and `mosque_cache_degraded_mode` Prometheus gauges. |
| **Data Integrity** | Valid 56/60-digit numeric payload parsed into ISO-8601 timestamps | **100%** strict schema validation | Automated `pytest` suite + weekly GitHub Actions cron testing live upstream HTML for contract drift. |

### Exposed Prometheus Metrics (`GET /metrics`)
* `mosque_upstream_fetch_total{status="success|error"}` *(Counter)*: Tracks upstream scrape reliability.
* `mosque_upstream_latency_seconds` *(Histogram)*: Tracks upstream response times across buckets.
* `mosque_cache_degraded_mode` *(Gauge)*: `0` when healthy; `1` when serving from fallback cache during an upstream failure.
* `mosque_cache_last_updated_timestamp_seconds` *(Gauge)*: Unix epoch timestamp of the last successful upstream scrape.

---

## 4. Repository Structure

```text
ha-call2prayer-sre-service/
├── .github/workflows/
│   └── ci.yml                   # Ruff lint, Pytest, Docker build & weekly live contract cron
├── docs/
│   ├── deployment.puml          # PlantUML Proxmox & Zero-Trust Firewall Deployment Diagram
│   ├── sequence_resilience.puml # PlantUML Retry & 72h Cache Fallback Sequence Diagram
│   └── cicd_activity.puml       # PlantUML CI/CD & Contract Testing Activity Diagram
├── homeassistant/
│   ├── configuration.yaml       # Enables Home Assistant packages directory
│   └── packages/
│       └── call2prayer.yaml     # Drop-in HA Package: 14 REST sensors, group, 3 scripts, 4 automations
├── src/
│   ├── __init__.py
│   ├── parser.py                # Pure regex extractor & 60-char string -> ISO-8601 dataclass 
│   ├── fetcher.py               # Tenacity exponential backoff, Prometheus metrics & 72h disk cache
│   └── main.py                  # FastAPI application (/api/v1/today, /healthz, /metrics)
├── tests/
│   └── test_parser.py           # Unit & schema contract tests using HTML snapshots
│   ├── test_fetcher.py          # Cache hit, cold start, 72h degradation, & self-healing tests
│   └── test_main.py             # FastAPI TestClient endpoint & HTTP status code tests (200/503)
│
├── Dockerfile                   # Multi-stage rootless container build (UID 10001)
├── docker-compose.yml           # Hardened Compose (read_only rootfs, cap_drop: ALL)
├── pyproject.toml               # Project metadata, dependencies & pytest config
└── README.md
```

---

## 5. Quickstart: Build Your Own Call2Prayer System

### Step 1: Clone & Run the Microservice (Docker Compose)
On your Linux server, LXC container, or Raspberry Pi:

```bash
git clone git@github.com:Aly-Hussein/ha-call2prayer-sre-service.git
cd ha-call2prayer-sre-service

# Build and launch the rootless container on port 8000
docker compose up -d --build

# Verify health, schedule output, and Prometheus metrics
curl -i http://localhost:8000/healthz
curl -s http://localhost:8000/api/v1/today | python3 -m json.tool
curl -s http://localhost:8000/metrics | grep mosque_
```

> **Customizing for Another Mosque:** If your local mosque also uses `mosqueprayertimes.com`, simply override the `MOSQUE_URL` environment variable in `docker-compose.yml` (e.g., `MOSQUE_URL=https://mosqueprayertimes.com/<your-mosque-slug>`) and adjust `TZ` in `src/parser.py`.

### Step 2: Install Audio Files in Home Assistant
1. In your Home Assistant `/config` directory, create the folder `/config/www/call2prayer/` (which Home Assistant exposes over HTTP as `/local/call2prayer/`).
2. Place your three MP3 audio files inside `/config/www/call2prayer/`:
   * `fajr-azan.mp3`
   * `regular-azan.mp3`
   * `iqama-reminder.mp3`

### Step 3: Deploy the Home Assistant Package
1. Ensure packages are enabled in your Home Assistant `/config/configuration.yaml`:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
2. Copy `homeassistant/packages/call2prayer.yaml` into `/config/packages/call2prayer.yaml`.
3. Update two values in `/config/packages/call2prayer.yaml` to match your environment:
   * Replace the `rest.resource` IP with your microservice host IP (`http://<PRAYER_API_HOST_IP>:8000/api/v1/today`).
   * Replace `media_player.living_room_speaker` with your smart speaker's entity ID.
4. In Home Assistant, navigate to **Developer Tools $\rightarrow$ YAML $\rightarrow$ Check Configuration** and click **Restart**.

### Step 4: Verify Chaos / Failure Recovery (Optional)
To verify graceful degradation:
1. Block outbound internet access on the Docker host (or set an invalid `MOSQUE_URL`).
2. Call `curl "http://localhost:8000/api/v1/today?refresh=true"`.
3. Confirm the API still returns `HTTP 200 OK` with `"cache_status": "DEGRADED_CACHE_FALLBACK"` and increments `mosque_cache_degraded_mode 1.0` in `/metrics`.

---

## 6. Local Development & Testing

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run linter and unit test suite
ruff check src/ tests/
pytest -v --cov=src

# Run local development server with hot-reload
export CACHE_FILE_PATH="./local_data/mpt_cache.json"
export PYTHONPATH="src"
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
# Interactive OpenAPI / Swagger UI available at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
```

---

## 7. License (Personal & Non-Commercial Use Only)

Copyright © 2026 Aly. All rights reserved.

This project is licensed under the **PolyForm Noncommercial License 1.0.0** (and documentation/diagrams under **CC BY-NC-SA 4.0**).
* **Permitted:** You are free to clone, fork, modify, and deploy this code for personal, homelab, educational, charitable, or non-profit religious use (e.g., mosques and community centers).
* **Prohibited:** You may **not** use this software, its architecture, or derivative works for commercial gain, paid products, or for-profit services without prior written permission from the author.

See the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0) for full legal terms.
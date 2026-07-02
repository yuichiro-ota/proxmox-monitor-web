import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .collector import fetch_report
from .notifier import is_configured, send_anomaly, send_scheduled, send_startup
from .scheduler import init as scheduler_init, shutdown as scheduler_shutdown
from .state import app_state, detect_anomalies, make_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
MONITOR_INTERVAL = 60  # seconds


async def _anomaly_monitor():
    while True:
        await asyncio.sleep(MONITOR_INTERVAL)
        if not app_state.notify_enabled or not is_configured():
            continue
        try:
            report = fetch_report()
            new_snap = make_snapshot(report)
            if app_state.last_snapshot:
                anomalies = detect_anomalies(app_state.last_snapshot, new_snap)
                if anomalies:
                    send_anomaly(anomalies)
            app_state.last_snapshot = new_snap
        except Exception as exc:
            log.error("Anomaly monitor error: %s", exc)


async def _scheduled_report():
    if not app_state.notify_enabled or not is_configured():
        return
    try:
        report = fetch_report()
        send_scheduled(report)
    except Exception as exc:
        log.error("Scheduled report error: %s", exc)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    try:
        report = fetch_report()
        app_state.last_snapshot = make_snapshot(report)
    except Exception as exc:
        log.warning("Could not initialize baseline snapshot: %s", exc)

    scheduler_init(
        lambda: asyncio.create_task(_scheduled_report()),
        lambda: asyncio.create_task(_scheduled_report()),
    )
    monitor = asyncio.create_task(_anomaly_monitor())

    yield

    monitor.cancel()
    scheduler_shutdown()


app = FastAPI(title="Proxmox Monitor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/latest")
def get_latest():
    try:
        return fetch_report()
    except Exception as exc:
        log.error("Failed to fetch from Proxmox: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/notify/status")
def get_notify_status():
    return {
        "enabled": app_state.notify_enabled,
        "webhook_configured": is_configured(),
    }


@app.post("/api/notify/toggle")
def toggle_notify():
    app_state.notify_enabled = not app_state.notify_enabled

    if app_state.notify_enabled and is_configured():
        try:
            report = fetch_report()
            app_state.last_snapshot = make_snapshot(report)
            send_startup(report)
        except Exception as exc:
            log.error("Failed to send activation notification: %s", exc)

    return {"enabled": app_state.notify_enabled}


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

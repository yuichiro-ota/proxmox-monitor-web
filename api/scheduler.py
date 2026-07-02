import logging
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

log = logging.getLogger(__name__)
JST = pytz.timezone("Asia/Tokyo")
_scheduler = AsyncIOScheduler(timezone=JST)


def init(monday_fn: Callable, friday_fn: Callable) -> None:
    _scheduler.add_job(
        monday_fn,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=JST),
        id="monday_report",
    )
    _scheduler.add_job(
        friday_fn,
        CronTrigger(day_of_week="fri", hour=18, minute=0, timezone=JST),
        id="friday_report",
    )
    _scheduler.start()
    log.info("Scheduler started: Mon 09:00 / Fri 18:00 JST")


def shutdown() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")

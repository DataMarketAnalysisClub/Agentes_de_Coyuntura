import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import get_settings
from jobs.high_impact_monitor import run_high_impact_monitor_once
from jobs.market_close import run_market_close
from jobs.morning_brief import run_morning_brief
from storage.database import init_db

logger = logging.getLogger(__name__)


def start_scheduler() -> None:
    """Start APScheduler with DMAC market brief jobs."""

    settings = get_settings()
    init_db(settings)
    scheduler = BlockingScheduler(timezone=settings.tz)
    scheduler.add_job(run_morning_brief, "cron", day_of_week="mon-fri", hour=8, minute=30, id="morning_brief")
    scheduler.add_job(run_market_close, "cron", day_of_week="mon-fri", hour=18, minute=30, id="market_close")
    if settings.alert_monitor_enabled:
        scheduler.add_job(run_high_impact_monitor_once, "interval", minutes=15, id="high_impact_monitor")
    else:
        logger.info("High impact monitor disabled")
    logger.info("Scheduler started", extra={"timezone": settings.tz})
    scheduler.start()

import argparse
import logging

from app.logging_config import configure_logging
from app.scheduler import start_scheduler
from jobs.high_impact_monitor import run_high_impact_monitor_once
from jobs.market_close import run_market_close
from jobs.morning_brief import run_morning_brief
from storage.database import init_db

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="DMAC market brief agent")
    parser.add_argument("command", choices=["morning", "close", "monitor-once", "scheduler"])
    args = parser.parse_args()

    configure_logging()
    init_db()

    if args.command == "morning":
        run_morning_brief()
    elif args.command == "close":
        run_market_close()
    elif args.command == "monitor-once":
        run_high_impact_monitor_once()
    elif args.command == "scheduler":
        start_scheduler()
    else:
        logger.error("Unknown command", extra={"command": args.command})


if __name__ == "__main__":
    main()

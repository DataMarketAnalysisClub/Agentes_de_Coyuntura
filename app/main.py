import argparse
import logging

from app.logging_config import configure_logging
from app.scheduler import start_scheduler
from jobs.ai_phase2_report import run_ai_phase2_report
from jobs.ai_phase3_editorial_email import run_ai_phase3_editorial_email
from jobs.ai_review_compare import run_ai_review_compare
from jobs.ai_review_fast import run_ai_review_fast
from jobs.ai_review_sample import run_ai_review_sample
from jobs.high_impact_monitor import run_high_impact_monitor_once
from jobs.market_close import run_market_close
from jobs.morning_brief import run_morning_brief
from storage.database import init_db

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="DMAC market brief agent")
    parser.add_argument(
        "command",
        choices=[
            "morning",
            "close",
            "monitor-once",
            "scheduler",
            "ai-phase2",
            "ai-phase3",
            "ai-review",
            "ai-review-fast",
            "ai-review-compare",
        ],
    )
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
    elif args.command == "ai-phase2":
        run_ai_phase2_report()
    elif args.command == "ai-phase3":
        run_ai_phase3_editorial_email()
    elif args.command == "ai-review":
        run_ai_review_sample()
    elif args.command == "ai-review-fast":
        run_ai_review_fast()
    elif args.command == "ai-review-compare":
        run_ai_review_compare()
    else:
        logger.error("Unknown command", extra={"command": args.command})


if __name__ == "__main__":
    main()

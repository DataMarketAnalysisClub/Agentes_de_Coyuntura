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
            "health",
            "web",
            "subscribers",
        ],
    )
    parser.add_argument(
        "args",
        nargs="*",
        help="subscribers: count | list [pending|active|unsubscribed] | add EMAIL | remove EMAIL | erase EMAIL",
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
    elif args.command == "health":
        from services.source_health_report import format_health_table
        from storage.repositories import SourceHealthRepository

        print(format_health_table(SourceHealthRepository().states()))
    elif args.command == "web":
        from app.subscription_server import run_subscription_server

        run_subscription_server()
    elif args.command == "subscribers":
        raise SystemExit(run_subscribers_command(args.args))
    else:
        logger.error("Unknown command", extra={"command": args.command})


def run_subscribers_command(argv: list[str], service=None) -> int:
    """Administracion de la lista de suscriptores (MySQL) por consola."""
    from services.subscriptions import SubscriptionService, UnsubscribeOutcome
    from storage.subscribers import SubscriberRepository, SubscriberStatus

    action, rest = (argv[0], argv[1:]) if argv else ("count", [])
    if service is None:
        repository = SubscriberRepository.from_settings()
        repository.init_schema()
        service = SubscriptionService(repository)
    repository = service.repository

    if action == "count" and not rest:
        for status, total in repository.counts_by_status().items():
            print(f"{status:<13} {total}")
        return 0
    if action == "list" and len(rest) <= 1:
        try:
            status = SubscriberStatus(rest[0]) if rest else None
        except ValueError:
            print(f"Estado desconocido: {rest[0]}")
            return 2
        for subscriber in repository.find(status):
            print(f"{subscriber.email}\t{subscriber.status}\t{subscriber.source}\t{subscriber.created_at:%Y-%m-%d}")
        return 0
    if action in {"add", "remove", "erase"} and len(rest) == 1:
        email = rest[0]
        if action == "add":
            try:
                subscriber = service.add_active(email)
            except ValueError as exc:
                print(exc)
                return 2
            print(f"Activo: {subscriber.email}")
        elif action == "remove":
            outcome = service.remove(email)
            print("No existe" if outcome is UnsubscribeOutcome.INVALID else f"Baja: {email}")
            return 1 if outcome is UnsubscribeOutcome.INVALID else 0
        else:
            erased = service.erase(email)
            print(f"Borrado con su historial: {email}" if erased else "No existe")
            return 0 if erased else 1
        return 0
    print("Uso: subscribers count | list [pending|active|unsubscribed] | add EMAIL | remove EMAIL | erase EMAIL")
    return 2


if __name__ == "__main__":
    main()

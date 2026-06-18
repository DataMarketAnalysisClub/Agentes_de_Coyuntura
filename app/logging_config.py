import json
import logging
import sys
from datetime import UTC, datetime
from logging import LogRecord


class JsonFormatter(logging.Formatter):
    """Small JSON formatter for structured application logs."""

    def format(self, record: LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

import json
import logging
import re
import sys
from datetime import UTC, datetime
from logging import LogRecord

SENSITIVE_KEYS: tuple[str, ...] = (
    "user",
    "pass",
    "password",
    "api_key",
    "apikey",
    "token",
    "authorization",
    "bearer",
    "smtp_password",
    "ollama_api_key",
    "bcentral_user",
    "bcentral_password",
)

_SENSITIVE_PATTERN = re.compile(
    r"((?:" + "|".join(re.escape(key) for key in SENSITIVE_KEYS) + r")\s*=\s*)([^\s&,'\"\]\)]+)",
    re.IGNORECASE,
)


def _redact_url(url: str) -> str:
    """Redact query params whose name matches sensitive keys."""
    if not url or "?" not in url:
        return url
    base, query = url.split("?", 1)
    safe_params: list[str] = []
    for raw_param in query.split("&"):
        if not raw_param:
            continue
        key, _, _value = raw_param.partition("=")
        if key.lower() in SENSITIVE_KEYS:
            safe_params.append(f"{key}=<redacted>")
        else:
            safe_params.append(raw_param)
    return f"{base}?{'&'.join(safe_params)}"


def _scrub_message(message: str) -> str:
    if not message:
        return message
    scrubbed = _SENSITIVE_PATTERN.sub(r"\1<redacted>", message)
    scrubbed = re.sub(
        r"(Authorization:\s*Bearer\s+)[A-Za-z0-9._\-]+",
        r"\1<redacted>",
        scrubbed,
        flags=re.IGNORECASE,
    )
    scrubbed = re.sub(
        r"https?://[^\s]+",
        lambda match: _redact_url(match.group(0)),
        scrubbed,
    )
    return scrubbed


class JsonFormatter(logging.Formatter):
    """Small JSON formatter for structured application logs."""

    def format(self, record: LogRecord) -> str:
        message = _scrub_message(record.getMessage())
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        for key, value in record.__dict__.items():
            if key in {"args", "asctime", "created", "exc_info", "exc_text", "filename",
                       "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                       "message", "msg", "name", "pathname", "process", "processName",
                       "relativeCreated", "stack_info", "thread", "threadName", "taskName"}:
                continue
            if key == "url" and isinstance(value, str):
                payload[key] = _redact_url(value)
            elif isinstance(value, str):
                payload[key] = _scrub_message(value)
            else:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class _UrlRedactFilter(logging.Filter):
    """Filter applied to noisy loggers (e.g. httpx) to scrub URLs."""

    def filter(self, record: LogRecord) -> bool:
        if isinstance(record.msg, str) and record.msg.startswith("HTTP Request:"):
            record.msg = _scrub_message(record.msg)
            record.args = ()
        if isinstance(record.args, dict):
            record.args = {
                key: _redact_url(value) if isinstance(value, str) and key == "url" else value
                for key, value in record.args.items()
            }
        elif record.args:
            record.args = tuple(
                _redact_url(value) if isinstance(value, str) else value
                for value in record.args
            )
        return True


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.WARNING)
    httpx_logger.addFilter(_UrlRedactFilter())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

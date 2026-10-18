import sys
from datetime import UTC

import structlog
from structlog.types import EventDict, Processor

from app.core.config import get_settings

settings = get_settings()


def add_severity_level(
    logger: structlog.BoundLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    event_dict["level"] = method_name.upper()
    return event_dict


def add_timestamp(
    logger: structlog.BoundLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    from datetime import datetime

    event_dict["timestamp"] = datetime.now(UTC).isoformat()
    return event_dict


def add_service_info(
    logger: structlog.BoundLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    event_dict["service"] = settings.OTEL_SERVICE_NAME
    event_dict["environment"] = settings.ENVIRONMENT
    return event_dict


def filter_sensitive_data(
    logger: structlog.BoundLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Redact secrets from the log event.

    Matching happens on the key name *and* on the value: a secret nested
    inside a payload (``{"headers": {"Authorization": "Bearer ..."}}``) is not
    covered by key-name matching alone.
    """
    sensitive_keys = {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "session",
        "private_key",
        "jwt",
        "bearer",
        "access_token",
        "refresh_token",
        "auth_config",
        "request_body",
        "prompt",
        "response",
    }

    def _is_sensitive(key: str) -> bool:
        lowered = key.lower()
        return any(sensitive in lowered for sensitive in sensitive_keys)

    def _redact_value(value):
        if isinstance(value, dict):
            return {k: ("***REDACTED***" if _is_sensitive(k) else _redact_value(v)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_redact_value(v) for v in value]
        if isinstance(value, str) and len(value) > 1000:
            return value[:1000] + "... [truncated]"
        return value

    filtered = {}
    for key, value in event_dict.items():
        if _is_sensitive(key):
            filtered[key] = "***REDACTED***"
        else:
            filtered[key] = _redact_value(value)
    return filtered


def setup_logging() -> None:
    """Configure structlog.

    This is called at import time of ``app.core.logging`` (and again from the
    application lifespan) so that loggers created during module import are
    bound to the configured processors. With
    ``cache_logger_on_first_use=True`` a logger that is created before
    ``setup_logging()`` runs would otherwise keep the default configuration
    for its whole lifetime.
    """
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_severity_level,
        add_timestamp,
        add_service_info,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        filter_sensitive_data,
    ]

    if settings.LOG_FORMAT == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    import logging

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    )


setup_logging()


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)

import logging
from logging.config import dictConfig


def configure_logging(level: str) -> None:
    """Configure application lifecycle logs without logging settings or requests."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "standard",
                }
            },
            "loggers": {
                "reliability_agent": {
                    "handlers": ["console"],
                    "level": level,
                    "propagate": False,
                }
            },
        }
    )
    # Third-party debug output can contain request details. Keep it at WARNING.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

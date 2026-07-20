import logging


class HealthCheckFilter(logging.Filter):
    """Suppress access-log noise from /health probes."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "/health" not in msg


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level)
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

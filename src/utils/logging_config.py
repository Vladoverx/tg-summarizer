import logging.config
import sys
from pathlib import Path


def setup_logging(log_dir: Path = Path("logs"), log_level: str = "INFO"):
    """
    Set up logging configuration for the application.
    
    Args:
        log_dir: Directory to store log files
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "app.log"

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "json": {
                "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(pathname)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "default",
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "level": log_level,
                "formatter": "json",
                "filename": str(log_file),
                "when": "midnight",
                "interval": 1,
                "backupCount": 7,  # Keep logs for 7 days
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console", "file"],
        },
        "loggers": {
            # Reduce noise from external libraries
            "httpx": {
                "level": "WARNING",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "telegram": {
                "level": "INFO",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "telethon": {
                "level": "WARNING",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "urllib3": {
                "level": "WARNING",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "sentence_transformers": {
                "level": "WARNING",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "transformers": {
                "level": "WARNING",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "torch": {
                "level": "WARNING",
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(LOGGING_CONFIG)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured - Level: {log_level}, File: {log_file}")
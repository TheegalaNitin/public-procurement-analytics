"""Shared logging configuration. Import get_logger anywhere you need to log."""
import logging
import sys
from config.settings import LOG_LEVEL, LOG_PATH

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        logging.basicConfig(
            level=LOG_LEVEL,
            format="%(asctime)s  %(levelname)-8s  %(name)-22s  %(message)s",
            handlers=[
                logging.FileHandler(LOG_PATH, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )
        _configured = True
    return logging.getLogger(name)

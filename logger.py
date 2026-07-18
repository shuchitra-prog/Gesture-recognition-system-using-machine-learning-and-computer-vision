# utils/logger.py
# Centralised logging configuration.

import logging
import sys
from config import LOG_PATH


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that writes to both stdout and a file."""
    logger = logging.getLogger(name)
    if logger.handlers:          # avoid duplicate handlers on reimport
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # File handler
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger

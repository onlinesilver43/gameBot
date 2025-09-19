from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


def init_logging(log_dir: str | None = None, level: str | int = "INFO") -> logging.Logger:
    """Initialize application logging with a rotating file and console handler.

    - log_dir: directory to store logs (default: ./logs)
    - level: logging level name or int
    Returns the root app logger named 'bot'.
    """
    name = "bot"
    logger = logging.getLogger(name)
    if logger.handlers:
        # Already configured
        return logger

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    log_dir = log_dir or os.environ.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(level)

    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console)

    logger.debug("Logging initialized at level %s; file=%s", level, log_path)
    return logger

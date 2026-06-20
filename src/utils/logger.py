import logging
import sys
from typing import Optional

from pythonjsonlogger import jsonlogger

DEFAULT_HANDLER = logging.StreamHandler(sys.stdout)
DEFAULT_FORMATTER = jsonlogger.JsonFormatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
DEFAULT_HANDLER.setFormatter(DEFAULT_FORMATTER)


def get_logger(name: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """
    Returns a configured logger instance with JSON formatting.
    Args:
        name (str, optional): Name of the logger. Defaults to None (root logger).
        level (int): Logging level. Defaults to logging.INFO.
    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Update the stream to the current sys.stdout to handle cases where
        # stdout has been replaced (e.g., by pytest's capsys)
        DEFAULT_HANDLER.setStream(sys.stdout)
        logger.addHandler(DEFAULT_HANDLER)
    logger.setLevel(level)
    logger.propagate = False
    return logger

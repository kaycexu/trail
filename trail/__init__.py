import logging

__all__ = ["__version__"]

__version__ = "0.1.0"

logger = logging.getLogger("trail")
logger.addHandler(logging.NullHandler())

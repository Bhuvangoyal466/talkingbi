import sys
from loguru import logger

# Remove default handler
logger.remove()

# Add console handler with structured format
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
    level="INFO",
    colorize=True,
)

# Add file handler for persistent logs
logger.add(
    "./data/cache/talkingbi.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} — {message}",
)

__all__ = ["logger"]

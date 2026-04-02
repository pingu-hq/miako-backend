import sys
import os
from loguru import logger

def setup_logger(log_level: str = "INFO"):
    logger.remove()
    logger.add(
        sys.stdout,
        format=("<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
                "| <level>{level: <8}</level> "
                "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
                "- <level>{message}</level>"),
        level=log_level,
        colorize=True,
        diagnose=False
    )

    log_dir = os.getenv("LOG_DIR", "/app/logs")
    os.makedirs(log_dir, exist_ok=True)
    logger.add(
        f"{log_dir}/app.log",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        level="DEBUG",
        encoding="utf-8",
    )

    return logger
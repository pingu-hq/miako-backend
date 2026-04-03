import sys
import os
from dotenv import load_dotenv
from loguru import logger as _logger

load_dotenv()


def setup_logger(log_level: str = "INFO"):
    """
    Configure loguru with:
    🔴 ERROR/CRITICAL → Red
    🟢 SUCCESS         → Green
    ⚪ INFO            → White
    🔵 DEBUG          → Cyan
    """
    _logger.remove()  # Remove default handler
    # After _logger.remove(), add icons without redefining severity:
    for level_name, icon in [
        ("DEBUG", "🔍"),
        ("INFO", "ℹ️"),
        ("SUCCESS", "✅"),
        ("WARNING", "⚠️"),
        ("ERROR", "❌"),
        ("CRITICAL", "🚨"),
    ]:
        try:
            _logger.level(level_name, icon=icon)
        except ValueError:
            pass  # Already exists, skip

    # ─────────────────────────────────────────────
    # 🎨 Color Format Templates
    # ─────────────────────────────────────────────
    # Update the console_format to include icon via {level.icon}
    console_format = (
        "<level>"
        "<red>{level: <8}</red></level> | "
        "<white>{time:YYYY-MM-DD HH:mm:ss}</white> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> → "
        "<level>{level.icon} {message}</level>"  # ← Add icon here!
    )

    # Custom level colors using loguru's <color> tags in message
    def colorize_message(record):
        """Inject color tags based on level for the message part only"""
        level = record["level"].name
        if level == "ERROR" or level == "CRITICAL":
            record["message"] = f"<red>{record['message']}</red>"
        elif level == "SUCCESS":
            record["message"] = f"<green>{record['message']}</green>"
        elif level == "INFO":
            record["message"] = f"<white>{record['message']}</white>"
        elif level == "DEBUG":
            record["message"] = f"<cyan>{record['message']}</cyan>"
        return True  # Always allow the record

    # ─────────────────────────────────────────────
    # 🖥️ Console Handler (Colored, Docker-friendly)
    # ─────────────────────────────────────────────
    _logger.add(
        sys.stdout,
        format=console_format,
        level=log_level,
        colorize=True,
        diagnose=False,
        filter=colorize_message,  # Apply custom message coloring
        enqueue=True
    )

    # ─────────────────────────────────────────────
    # 📁 File Handler (Plain text, no ANSI codes)
    # ─────────────────────────────────────────────
    log_dir = os.getenv("LOG_DIR", "/app/logs")
    os.makedirs(log_dir, exist_ok=True)

    # Single file for all logs (simple & Docker-safe)
    _logger.add(
        f"{log_dir}/app.log",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        level="DEBUG",  # Capture everything
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        colorize=False  # ← Important: files don't render ANSI colors well
    )

    # ─────────────────────────────────────────────
    # 🔴 Optional: Separate Error-Only File
    # ─────────────────────────────────────────────
    # Uncomment if you want errors isolated for monitoring
    _logger.add(
        f"{log_dir}/errors.log",
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        colorize=False
    )

    return _logger


# Initialize logger
logger = setup_logger(os.getenv("LOG_LEVEL", "INFO"))

# At the very end of core/logger.py, after logger init:
# logger.debug(f"🔍 Logger initialized with level: {os.getenv('LOG_LEVEL', 'INFO')}")
logger.debug("🔍 Debug message")      # 🔵 Cyan
logger.info("ℹ️  Info message")        # ⚪ White
logger.success("✅ Success message")   # 🟢 Green + ✅ icon
logger.warning("⚠️  Warning")          # 🟡 Yellow
logger.error("❌ Error occurred")      # 🔴 Red

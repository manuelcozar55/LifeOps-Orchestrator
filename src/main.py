import os
import asyncio
from dotenv import load_dotenv
import structlog

load_dotenv()
logger = structlog.get_logger()

if __name__ == "__main__":
    try:
        # Standard startup sequence
        logger.info("Starting LifeOps Orchestrator", service="orchestrator")
        from src.tools.telegram_bot import get_telegram_app
        app = get_telegram_app()
        logger.info("Starting Telegram polling...")
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Shutting down Orchestrator due to KeyboardInterrupt")
    except Exception as e:
        logger.error("Terminal crash in Orchestrator", error=str(e))

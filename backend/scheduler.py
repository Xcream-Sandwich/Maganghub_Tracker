import asyncio
import logging
from backend.sync_service import sync_all

logger = logging.getLogger(__name__)

async def start_periodic_sync(interval_hours=3):
    logger.info(f"Background scheduler started (interval: {interval_hours} hours).")
    while True:
        try:
            logger.info("Executing periodic sync check...")
            # Non-blocking run in threadpool
            result = await asyncio.to_thread(sync_all, force=False)
            logger.info(f"Periodic sync result: {result.get('status')} - {result.get('message', '')}")
        except Exception as e:
            logger.error(f"Error in background sync: {e}")
        
        await asyncio.sleep(interval_hours * 3600)

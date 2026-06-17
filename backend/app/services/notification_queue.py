import asyncio
import logging

from app.services.email import send_alert_email
from app.services.telegram import send_telegram_message

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[dict] = asyncio.Queue()
_workers: list[asyncio.Task] = []


async def _worker_loop():
    while True:
        job = await _queue.get()
        fut: asyncio.Future = job["future"]
        try:
            if job["channel"] == "telegram":
                ok = await send_telegram_message(job["chat_id"], job["text"])
            else:
                ok = await send_alert_email(job["to"], job["subject"], job["html"], job.get("text"))
            fut.set_result(bool(ok))
        except Exception as exc:
            logger.error("Notification queue worker failed: %s", exc)
            if not fut.done():
                fut.set_result(False)
        finally:
            _queue.task_done()


def start_notification_workers(count: int = 4):
    global _workers
    if _workers:
        return
    for _ in range(max(1, count)):
        _workers.append(asyncio.create_task(_worker_loop()))


async def stop_notification_workers():
    global _workers
    for task in _workers:
        task.cancel()
    _workers = []


async def enqueue_telegram(chat_id: str, text: str) -> bool:
    fut = asyncio.get_running_loop().create_future()
    await _queue.put({"channel": "telegram", "chat_id": chat_id, "text": text, "future": fut})
    return await fut


async def enqueue_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    fut = asyncio.get_running_loop().create_future()
    await _queue.put({"channel": "email", "to": to, "subject": subject, "html": html, "text": text, "future": fut})
    return await fut

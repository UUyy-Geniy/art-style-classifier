from __future__ import annotations

import asyncio
import logging

import aio_pika

from artstyle_backend.core.config import get_settings
from artstyle_backend.core.database import SessionLocal, engine
from artstyle_backend.ml.loader import ModelManager
from artstyle_backend.schemas.messages import InferenceTaskMessage
from artstyle_backend.services.bootstrap import ensure_seed_data
from artstyle_backend.services.storage import StorageService
from artstyle_backend.services.tasks import mark_task_failed, mark_task_processing, persist_prediction_result

logger = logging.getLogger(__name__)


async def process_message(
    message: aio_pika.abc.AbstractIncomingMessage,
    storage: StorageService,
    model_manager: ModelManager,
) -> None:
    payload = InferenceTaskMessage.model_validate_json(message.body)

    async with message.process(requeue=False):
        async with SessionLocal() as session:
            await mark_task_processing(session, payload.task_id)

        try:
            model = await model_manager.ensure_current_model()
            image_bytes = await storage.download_bytes(payload.s3_key)
            predictions = await asyncio.to_thread(model.predict, image_bytes, payload.top_k)
            async with SessionLocal() as session:
                await persist_prediction_result(
                    session=session,
                    task_id=payload.task_id,
                    model_name=model.model_name,
                    model_version=model.model_version,
                    model_source=model.model_source,
                    candidates_payload=predictions,
                )
        except Exception as exc:
            logger.exception("Inference task %s failed.", payload.task_id)
            async with SessionLocal() as session:
                await mark_task_failed(session, payload.task_id, str(exc))


async def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    async with SessionLocal() as session:
        await ensure_seed_data(session)

    storage = StorageService(settings)
    model_manager = ModelManager(settings, SessionLocal)
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(settings.rabbitmq_queue_name, durable=True)

    try:
        async with queue.iterator() as iterator:
            async for message in iterator:
                await process_message(message, storage, model_manager)
    finally:
        await channel.close()
        await connection.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()

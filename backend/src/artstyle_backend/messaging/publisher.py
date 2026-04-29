from __future__ import annotations

import aio_pika

from artstyle_backend.core.config import Settings
from artstyle_backend.schemas.messages import InferenceTaskMessage


class RabbitMQPublisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.declare_queue(self._settings.rabbitmq_queue_name, durable=True)
        self._exchange = self._channel.default_exchange

    async def publish_task(self, message: InferenceTaskMessage) -> None:
        if self._exchange is None:
            raise RuntimeError("RabbitMQ publisher is not connected.")
        await self._exchange.publish(
            aio_pika.Message(
                body=message.model_dump_json().encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=self._settings.rabbitmq_queue_name,
        )

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        if self._connection is not None:
            await self._connection.close()


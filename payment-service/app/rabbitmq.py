import json

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractRobustConnection,
)


async def connect_rabbitmq(url: str) -> AbstractRobustConnection:
    return await aio_pika.connect_robust(url)


async def declare_payment_exchange(
    channel: AbstractChannel,
    exchange_name: str,
) -> AbstractExchange:
    return await channel.declare_exchange(
        exchange_name,
        type=aio_pika.ExchangeType.DIRECT,
        durable=True,
    )


async def event_publish_json(
    exchange: AbstractExchange,
    routing_key: str,
    data: dict,
):
    message = aio_pika.Message(
        body=json.dumps(data).encode("utf-8"),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )

    await exchange.publish(
        message,
        routing_key=routing_key,
    )
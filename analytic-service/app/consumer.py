import json

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from pymongo.asynchronous.collection import AsyncCollection

from .config import settings


async def save_event(
    collection: AsyncCollection,
    message: ConsumerRecord,
):
    event = json.loads(message.value)

    await collection.update_one(
        {"event_id": event["event_id"]},
        {"$setOnInsert": event},
        upsert=True,
    )


async def consume_events(collection: AsyncCollection):
    await collection.create_index(
        "event_id",
        unique=True,
    )

    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="orderflow-analytics",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )

    try:
        await consumer.start()

        async for message in consumer:
            await save_event(collection, message)
            await consumer.commit()

            print(
                "Событие обработано:",
                f"partition={message.partition}",
                f"offset={message.offset}",
                flush=True,
            )
    finally:
        await consumer.stop()
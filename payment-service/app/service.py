import asyncio

from aio_pika.abc import AbstractExchange
from aiokafka import AIOKafkaProducer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PaymentORM
from .config import NotFoundError, settings
from .schemas import PaymentCreateSchema, PaymentReadSchema
from .events import build_payment_succeeded_event
from .rabbitmq import event_publish_json
from .kafka import publish_kafka_event


class PaymentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        payment_data: PaymentCreateSchema,
    ) -> PaymentORM:
        payment = PaymentORM(
            order_id=payment_data.order_id,
            status="created",
            amount=payment_data.amount,
        )

        self.session.add(payment)
        await self.session.commit()

        return payment

    async def get(self, payment_id: str) -> PaymentORM:
        payment = await self.session.get(PaymentORM, payment_id)

        if payment is None:
            raise NotFoundError

        return payment

    async def get_all(self) -> list[PaymentORM]:
        stmt = select(PaymentORM)
        result = await self.session.scalars(stmt)

        return list(result.all())

    async def complete_payment(
        self,
        payment: PaymentORM,
        exchange: AbstractExchange,
        kafka_producer: AIOKafkaProducer,
    ) -> PaymentReadSchema:
        await asyncio.sleep(4)

        payment.status = "succeeded"
        await self.session.commit()

        event = build_payment_succeeded_event(
            payment_id=payment.id,
            order_id=payment.order_id,
            amount=payment.amount,
        )

        await event_publish_json(
            exchange=exchange,
            routing_key=settings.payment_succeeded_routing_key,
            data=event,
        )

        await publish_kafka_event(
            producer=kafka_producer,
            topic=settings.kafka_analytic_payment_topic,
            event=event,
        )

        return PaymentReadSchema.model_validate(payment)
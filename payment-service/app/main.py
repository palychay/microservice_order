from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.config import NotFoundError, settings
from app.database import engine
from app.models import Base
from app.schemas import PaymentCreateSchema, PaymentReadSchema
from app.service import PaymentService
from app.dependencies import get_payment_service
from app.rabbitmq import connect_rabbitmq, declare_payment_exchange
from app.kafka import create_kafka_producer


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    rabbitmq_connection = await connect_rabbitmq(
        settings.rabbitmq_url,
    )

    try:
        channel = await rabbitmq_connection.channel()

        app.state.payment_exchange = await declare_payment_exchange(
            channel,
            settings.payment_exchange_name,
        )

        kafka_producer = create_kafka_producer()

        try:
            await kafka_producer.start()
            app.state.kafka_producer = kafka_producer

            yield
        finally:
            await kafka_producer.stop()
    finally:
        try:
            await rabbitmq_connection.close()
        finally:
            await engine.dispose()


app = FastAPI(lifespan=lifespan)


@app.get("/payments/{payment_id}", response_model=PaymentReadSchema)
async def get_payment(
    payment_id: str,
    payment_service: PaymentService = Depends(get_payment_service),
):
    try:
        return await payment_service.get(payment_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Платёж не найден",
        )


@app.get("/payments", response_model=list[PaymentReadSchema])
async def get_payments(
    payment_service: PaymentService = Depends(get_payment_service),
):
    return await payment_service.get_all()


@app.post(
    "/payments",
    response_model=PaymentReadSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    request: Request,
    payload: PaymentCreateSchema,
    payment_service: PaymentService = Depends(get_payment_service),
):
    payment = await payment_service.create(payload)

    return await payment_service.complete_payment(
        payment=payment,
        exchange=request.app.state.payment_exchange,
        kafka_producer=request.app.state.kafka_producer,
    )
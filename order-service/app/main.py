from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, status

from app.config import NotFoundError
from app.database import engine
from app.models import Base
from app.schemas import OrderCreateSchema, OrderReadSchema
from app.service import OrderService
from app.dependencies import get_order_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/orders/{order_id}", response_model=OrderReadSchema)
def get_order(
    order_id: str,
    order_service: OrderService = Depends(get_order_service),
):
    try:
        return order_service.get(order_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заказ не найден",
        )


@app.get("/orders", response_model=list[OrderReadSchema])
def get_orders(
    order_service: OrderService = Depends(get_order_service),
):
    return order_service.get_all()


@app.post(
    "/orders",
    response_model=OrderReadSchema,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    payload: OrderCreateSchema,
    order_service: OrderService = Depends(get_order_service),
):
    try:
        return order_service.create(payload)

    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Один из товаров не найден",
            )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ошибка ответа каталога",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Каталог недоступен",
        )
    
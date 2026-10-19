from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.service import PaymentService


def get_payment_service(
    db: AsyncSession = Depends(get_db),
) -> PaymentService:
    return PaymentService(db)
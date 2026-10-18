from fastapi import Depends
from sqlalchemy.orm import Session

from app.api_clients import CatalogClient
from app.database import get_db
from app.service import OrderService
from app.config import settings


def get_catalog_client() -> CatalogClient:
    return CatalogClient(
        base_url=settings.catalog_service_url,
    )


def get_order_service(
    db: Session = Depends(get_db),
    catalog_client: CatalogClient = Depends(get_catalog_client),
) -> OrderService:
    return OrderService(db, catalog_client)
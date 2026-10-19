from pydantic import BaseModel, ConfigDict, Field


class PaymentCreateSchema(BaseModel):
    order_id: str
    amount: int = Field(gt=0)


class PaymentReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    status: str
    amount: int
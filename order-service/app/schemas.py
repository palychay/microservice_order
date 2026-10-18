from pydantic import BaseModel, ConfigDict, Field


class OrderItemCreateSchema(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class OrderCreateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    items: list[OrderItemCreateSchema] = Field(min_length=1)


class OrderItemReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    product_name: str
    quantity: int
    unit_price: int


class OrderReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    status: str
    total_amount: int
    items: list[OrderItemReadSchema]
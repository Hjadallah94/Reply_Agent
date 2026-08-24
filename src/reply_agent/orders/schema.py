from datetime import datetime

from pydantic import BaseModel


class OrderRecord(BaseModel):
    order_reference: str
    customer_phone: str  # already normalized (orders/phone.py) by the time this is built
    customer_name: str | None = None
    status: str
    items_summary: str | None = None
    order_date: datetime | None = None

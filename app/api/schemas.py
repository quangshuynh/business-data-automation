from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """response model for application health"""

    status: str


class CustomerResponse(BaseModel):
    """response model for a customer"""

    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    name: str
    email: str
    phone: str


class OrderResponse(BaseModel):
    """response model for an order"""

    model_config = ConfigDict(from_attributes=True)

    order_id: int
    customer_id: int
    date: date
    total: Decimal


class PaymentResponse(BaseModel):
    """response model for a payment"""

    model_config = ConfigDict(from_attributes=True)

    payment_id: int
    order_id: int
    amount: Decimal
    status: str


class ReconciliationResponse(BaseModel):
    """response model for a reconciled order"""

    order_id: int
    customer_id: int
    date: date
    total: Decimal
    name: str
    email: str
    phone: str
    amount_paid: Decimal
    payment_count: int
    balance_due: Decimal
    outstanding_balance: Decimal
    overpayment_amount: Decimal
    customer_found: bool
    financial_status: str
    discrepancy_flags: str
    reconciliation_timestamp: datetime

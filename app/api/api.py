from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.api.schemas import (
    CustomerResponse,
    HealthResponse,
    OrderResponse,
    PaymentResponse,
    ReconciliationResponse,
)
from app.db.models import Customer, Order, Payment
from app.reconciliation.reconcile import build_report


api = FastAPI(
    title="Business Data Automation API",
    version="1.0.0",
)

DatabaseSession = Annotated[Session, Depends(get_database_session)]


@api.get("/health", response_model=HealthResponse)
def health_check():
    """
    returns the application health status
    :returns: dictionary containing the application health status
    """
    return {"status": "ok"}


@api.get("/customers", response_model=list[CustomerResponse])
def list_customers(session: DatabaseSession):
    """
    returns customers stored in the database
    :param session: SQLAlchemy database session
    :returns: list of customers ordered by customer id
    """
    statement = select(Customer).order_by(Customer.customer_id)
    return list(session.scalars(statement))


@api.get("/orders", response_model=list[OrderResponse])
def list_orders(session: DatabaseSession):
    """
    returns orders stored in the database
    :param session: SQLAlchemy database session
    :returns: list of orders ordered by order id
    """
    statement = select(Order).order_by(Order.order_id)
    return list(session.scalars(statement))


@api.get("/payments", response_model=list[PaymentResponse])
def list_payments(session: DatabaseSession):
    """
    returns payments stored in the database
    :param session: SQLAlchemy database session
    :returns: list of payments ordered by payment id
    """
    statement = select(Payment).order_by(Payment.payment_id)
    return list(session.scalars(statement))


@api.get("/reconciliation", response_model=list[ReconciliationResponse])
def list_reconciliation_results(session: DatabaseSession):
    """
    returns reconciliation results calculated from persisted records
    :param session: SQLAlchemy database session
    :returns: list of reconciled orders ordered by order id
    """
    customers = list(session.scalars(select(Customer).order_by(Customer.customer_id)))
    orders = list(session.scalars(select(Order).order_by(Order.order_id)))
    payments = list(session.scalars(select(Payment).order_by(Payment.payment_id)))

    if not orders:
        return []

    customer_data = pd.DataFrame(
        [
            {
                "customer_id": customer.customer_id,
                "name": customer.name,
                "email": customer.email,
                "phone": customer.phone,
            }
            for customer in customers
        ],
        columns=["customer_id", "name", "email", "phone"],
    )
    order_data = pd.DataFrame(
        [
            {
                "order_id": order.order_id,
                "customer_id": order.customer_id,
                "date": order.date,
                "total": order.total,
            }
            for order in orders
        ],
        columns=["order_id", "customer_id", "date", "total"],
    )
    payment_data = pd.DataFrame(
        [
            {
                "payment_id": payment.payment_id,
                "order_id": payment.order_id,
                "amount": payment.amount,
                "status": payment.status,
            }
            for payment in payments
        ],
        columns=["payment_id", "order_id", "amount", "status"],
    )

    report = build_report(customer_data, order_data, payment_data)
    return report.to_dict(orient="records")

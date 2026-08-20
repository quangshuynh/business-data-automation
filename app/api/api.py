from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
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
from app.services.reconciliation_service import build_persisted_reconciliation


api = FastAPI(
    title="Business Data Automation API",
    version="1.0.0",
)

DatabaseSession = Annotated[Session, Depends(get_database_session)]
DASHBOARD_DIR = Path(__file__).parents[1] / "dashboard"


@api.get("/", include_in_schema=False)
def dashboard_redirect():
    """
    redirects the application root to the dashboard
    :returns: redirect response for the dashboard
    """
    return RedirectResponse(url="/dashboard/")


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
    return build_persisted_reconciliation(session)


api.mount(
    "/dashboard",
    StaticFiles(directory=DASHBOARD_DIR, html=True),
    name="dashboard",
)

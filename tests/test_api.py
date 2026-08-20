from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.api import api
from app.api.dependencies import get_api_engine, get_database_session
from app.db.models import Base, Customer, Order, Payment


@pytest.fixture
def api_client():
    """
    creates an API client backed by an isolated in-memory database
    :returns: FastAPI test client containing sample business records
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Customer(
                customer_id=1001,
                name="John Smith",
                email="john@example.com",
                phone="(585) 555-1234",
            )
        )
        session.add_all(
            [
                Order(
                    order_id=5001,
                    customer_id=1001,
                    date=date(2026, 8, 1),
                    total=Decimal("100.00"),
                ),
                Order(
                    order_id=5002,
                    customer_id=1001,
                    date=date(2026, 8, 2),
                    total=Decimal("75.00"),
                ),
            ]
        )
        session.add(
            Payment(
                payment_id=9001,
                order_id=5001,
                amount=Decimal("100.00"),
                status="paid",
            )
        )
        session.commit()

    def override_database_session():
        """
        provides an isolated database session for an API test
        :returns: SQLAlchemy database session
        """
        with Session(engine) as session:
            yield session

    api.dependency_overrides[get_database_session] = override_database_session

    with TestClient(api) as client:
        yield client

    api.dependency_overrides.clear()
    engine.dispose()


def test_health_check(api_client):
    """
    tests that the health endpoint reports the application as available
    :param api_client: FastAPI client backed by a test database
    :returns: none
    """
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_business_records(api_client):
    """
    tests that customer order and payment endpoints return stored records
    :param api_client: FastAPI client backed by a test database
    :returns: none
    """
    customers = api_client.get("/customers")
    orders = api_client.get("/orders")
    payments = api_client.get("/payments")

    assert customers.status_code == 200
    assert customers.json()[0]["email"] == "john@example.com"
    assert orders.status_code == 200
    assert [order["order_id"] for order in orders.json()] == [5001, 5002]
    assert payments.status_code == 200
    assert payments.json()[0]["status"] == "paid"


def test_reconciliation_uses_persisted_records(api_client):
    """
    tests that the reconciliation endpoint calculates stored order balances
    :param api_client: FastAPI client backed by a test database
    :returns: none
    """
    response = api_client.get("/reconciliation")

    assert response.status_code == 200
    results = {row["order_id"]: row for row in response.json()}

    assert results[5001]["financial_status"] == "paid"
    assert results[5001]["payment_count"] == 1
    assert float(results[5001]["balance_due"]) == 0.00
    assert results[5002]["financial_status"] == "unpaid"
    assert float(results[5002]["balance_due"]) == 75.00
    assert results[5002]["discrepancy_flags"] == "order has no payments"


def test_data_endpoint_handles_missing_database_configuration(monkeypatch):
    """
    tests that data endpoints report unavailable database configuration
    :param monkeypatch: pytest fixture for changing environment variables
    :returns: none
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_api_engine.cache_clear()

    with TestClient(api) as client:
        response = client.get("/customers")

    assert response.status_code == 503
    assert response.json() == {"detail": "database is not available"}

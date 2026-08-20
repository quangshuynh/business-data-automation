from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_database_url, is_database_configured
from app.db import database, persistence
from app.db.models import Base, Customer, Order, Payment
from app.db.persistence import DatabasePersistenceError, persist_valid_data


def test_get_database_url_reads_environment_variable(monkeypatch):
    """
    tests that database configuration is read from the environment
    :param monkeypatch: pytest fixture for changing environment variables
    :returns: none
    """
    database_url = "postgresql+psycopg://user:password@localhost/business_data"
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert get_database_url() == database_url


def test_get_database_url_requires_environment_variable(monkeypatch):
    """
    tests that missing database configuration raises an error
    :param monkeypatch: pytest fixture for changing environment variables
    :returns: none
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(
        ValueError,
        match="DATABASE_URL environment variable is required",
    ):
        get_database_url()


def test_get_database_url_rejects_invalid_connection_format(monkeypatch):
    """
    tests that database configuration requires the Psycopg connection format
    :param monkeypatch: pytest fixture for changing environment variables
    :returns: none
    """
    monkeypatch.setenv("DATABASE_URL", "mysql://user:password@localhost/database")

    with pytest.raises(
        ValueError,
        match="DATABASE_URL must use the postgresql\\+psycopg:// connection format",
    ):
        get_database_url()


def test_is_database_configured_reflects_environment(monkeypatch):
    """
    tests that optional persistence detects database configuration
    :param monkeypatch: pytest fixture for changing environment variables
    :returns: none
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert is_database_configured() is False

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://configured")
    assert is_database_configured() is True


def test_models_define_tables_and_relationships():
    """
    tests that models define required tables and foreign keys
    :returns: none
    """
    assert set(Base.metadata.tables) == {"customers", "orders", "payments"}

    order_foreign_keys = {key.target_fullname for key in Order.__table__.foreign_keys}
    payment_foreign_keys = {
        key.target_fullname for key in Payment.__table__.foreign_keys
    }

    assert order_foreign_keys == {"customers.customer_id"}
    assert payment_foreign_keys == {"orders.order_id"}
    assert Order.__table__.c.total.type.precision == 12
    assert Order.__table__.c.total.type.scale == 2


def test_initialize_database_creates_model_tables():
    """
    tests that database initialization creates all model tables
    :returns: none
    """
    engine = create_engine("sqlite:///:memory:")

    database.initialize_database(engine)

    assert set(inspect(engine).get_table_names()) == {
        "customers",
        "orders",
        "payments",
    }


def test_database_session_commits_and_closes():
    """
    tests that a successful database session commits and closes
    :returns: none
    """
    session = MagicMock()

    with database.database_session(lambda: session) as active_session:
        assert active_session is session

    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()
    session.close.assert_called_once_with()


def test_database_session_rolls_back_on_error():
    """
    tests that a failed database session rolls back and closes
    :returns: none
    """
    session = MagicMock()

    with pytest.raises(RuntimeError, match="database failure"):
        with database.database_session(lambda: session):
            raise RuntimeError("database failure")

    session.commit.assert_not_called()
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


def test_persist_valid_data_inserts_records_without_duplicates():
    """
    tests that repeated persistence updates records without creating duplicates
    :returns: none
    """
    engine = create_engine("sqlite:///:memory:")

    customers = pd.DataFrame(
        [
            {
                "customer_id": 1001,
                "name": "John Smith",
                "email": "john@example.com",
                "phone": "(585) 555-1234",
                "email_valid": True,
                "phone_valid": True,
            }
        ]
    )
    orders = pd.DataFrame(
        [
            {
                "order_id": 5001,
                "customer_id": 1001,
                "date": pd.Timestamp("2026-08-01"),
                "total": 100.00,
            }
        ]
    )
    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001,
                "order_id": 5001,
                "amount": 100.00,
                "transaction_type": "payment",
                "status": "paid",
            }
        ]
    )

    first_counts = persist_valid_data(customers, orders, payments, engine)
    customers.loc[0, "name"] = "John A. Smith"
    second_counts = persist_valid_data(customers, orders, payments, engine)

    assert first_counts == {"customers": 1, "orders": 1, "payments": 1}
    assert second_counts == first_counts

    with Session(engine) as session:
        customer = session.scalar(select(Customer))
        order = session.scalar(select(Order))
        payment = session.scalar(select(Payment))

        assert len(session.scalars(select(Customer)).all()) == 1
        assert len(session.scalars(select(Order)).all()) == 1
        assert len(session.scalars(select(Payment)).all()) == 1
        assert customer.name == "John A. Smith"
        assert customer.email == "john@example.com"
        assert order.date == date(2026, 8, 1)
        assert float(order.total) == 100.00
        assert payment.transaction_type == "payment"
        assert payment.status == "paid"


@pytest.mark.parametrize(
    ("amount", "transaction_type", "payment_status"),
    [
        (100.00, "payment", "unsupported"),
        (-10.00, "refund", "refunded"),
        (10.00, "unknown", "paid"),
    ],
)
def test_database_rejects_invalid_payment_data(
    amount,
    transaction_type,
    payment_status,
):
    """
    tests that database constraints reject invalid payment transaction data
    :param amount: transaction amount to store
    :param transaction_type: transaction type to store
    :param payment_status: source payment status to store
    :returns: none
    """
    engine = create_engine("sqlite:///:memory:")
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
        session.add(
            Order(
                order_id=5001,
                customer_id=1001,
                date=date(2026, 8, 1),
                total=100.00,
            )
        )
        session.add(
            Payment(
                payment_id=9001,
                order_id=5001,
                amount=amount,
                transaction_type=transaction_type,
                status=payment_status,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_database_enforces_foreign_keys_when_enabled():
    """
    tests that the relational schema rejects an order with no customer parent
    :returns: none
    """
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Order(
                order_id=5001,
                customer_id=9999,
                date=date(2026, 8, 1),
                total=100.00,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_persistence_wraps_database_configuration_errors(monkeypatch):
    """
    tests that database configuration failures use the persistence error contract
    :param monkeypatch: pytest fixture for replacing engine creation
    :returns: none
    """
    monkeypatch.setattr(
        persistence,
        "create_database_engine",
        MagicMock(side_effect=ValueError("invalid database url")),
    )
    empty_frame = pd.DataFrame()

    with pytest.raises(
        DatabasePersistenceError,
        match="validated records could not be persisted",
    ):
        persist_valid_data(empty_frame, empty_frame, empty_frame)

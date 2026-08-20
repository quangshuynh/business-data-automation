from sqlalchemy.exc import SQLAlchemyError

from app.db.database import (
    create_database_engine,
    create_session_factory,
    database_session,
    initialize_database,
)
from app.db.models import Customer, Order, Payment


class DatabasePersistenceError(Exception):
    """error raised when validated records cannot be persisted"""


def insert_customers(session, customers):
    """
    adds validated customer records to a database session
    :param session: SQLAlchemy database session
    :param customers: dataframe containing validated customers
    :returns: number of customer records added
    """
    records = customers.to_dict(orient="records")
    for record in records:
        session.merge(
            Customer(
                customer_id=record["customer_id"],
                name=record["name"],
                email=record["email"],
                phone=record["phone"],
            )
        )
    return len(records)


def insert_orders(session, orders):
    """
    adds validated order records to a database session
    :param session: SQLAlchemy database session
    :param orders: dataframe containing validated orders
    :returns: number of order records added
    """
    records = orders.to_dict(orient="records")
    for record in records:
        session.merge(
            Order(
                order_id=record["order_id"],
                customer_id=record["customer_id"],
                date=record["date"].date()
                if hasattr(record["date"], "date")
                else record["date"],
                total=record["total"],
            )
        )
    return len(records)


def insert_payments(session, payments):
    """
    adds validated payment records to a database session
    :param session: SQLAlchemy database session
    :param payments: dataframe containing validated payments
    :returns: number of payment records added
    """
    records = payments.to_dict(orient="records")
    for record in records:
        session.merge(
            Payment(
                payment_id=record["payment_id"],
                order_id=record["order_id"],
                amount=record["amount"],
                status=record["status"],
            )
        )
    return len(records)


def persist_valid_data(customers, orders, payments, engine=None):
    """
    persists validated pipeline records in a single database transaction
    :param customers: dataframe containing validated customers
    :param orders: dataframe containing validated orders
    :param payments: dataframe containing validated payments
    :param engine: optional SQLAlchemy database engine
    :returns: dictionary containing persisted record counts
    """
    database_engine = engine or create_database_engine()
    owns_engine = engine is None

    try:
        initialize_database(database_engine)
        session_factory = create_session_factory(database_engine)

        with database_session(session_factory) as session:
            counts = {
                "customers": insert_customers(session, customers),
                "orders": insert_orders(session, orders),
                "payments": insert_payments(session, payments),
            }

        return counts
    except SQLAlchemyError as error:
        raise DatabasePersistenceError(
            "validated records could not be persisted"
        ) from error
    finally:
        if owns_engine:
            database_engine.dispose()

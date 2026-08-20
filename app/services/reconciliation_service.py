import pandas as pd
from sqlalchemy import select

from app.db.models import Customer, Order, Payment
from app.reconciliation.reconcile import build_report


def build_persisted_reconciliation(session):
    """
    builds reconciliation results from records stored in the database
    :param session: SQLAlchemy database session
    :returns: list of reconciled order dictionaries ordered by order id
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

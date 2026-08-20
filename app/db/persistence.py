from app.db.models import Customer, Order, Payment


def insert_customers(session, customers):
    """
    adds validated customer records to a database session
    :param session: SQLAlchemy database session
    :param customers: dataframe containing validated customers
    :returns: number of customer records added
    """
    records = customers.to_dict(orient="records")
    session.add_all(
        Customer(
            customer_id=record["customer_id"],
            name=record["name"],
            email=record["email"],
            phone=record["phone"],
        )
        for record in records
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
    session.add_all(
        Order(
            order_id=record["order_id"],
            customer_id=record["customer_id"],
            date=record["date"].date()
            if hasattr(record["date"], "date")
            else record["date"],
            total=record["total"],
        )
        for record in records
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
    session.add_all(
        Payment(
            payment_id=record["payment_id"],
            order_id=record["order_id"],
            amount=record["amount"],
            status=record["status"],
        )
        for record in records
    )
    return len(records)

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Numeric, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """base class for database models"""


class Customer(Base):
    """database model for a validated customer"""

    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Order(Base):
    """database model for a validated order"""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total > 0", name="orders_total_positive"),
    )

    order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="RESTRICT"),
        nullable=False,
    )
    date: Mapped[date_type] = mapped_column("order_date", Date, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="orders")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")


class Payment(Base):
    """database model for a validated payment"""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "(transaction_type IN ('payment', 'refund') AND amount > 0) "
            "OR (transaction_type = 'adjustment' AND amount <> 0)",
            name="payments_transaction_amount_valid",
        ),
        CheckConstraint(
            "transaction_type IN ('payment', 'refund', 'adjustment')",
            name="payments_transaction_type_allowed",
        ),
        CheckConstraint(
            "status IN ('paid', 'partial', 'pending', 'refunded')",
            name="payments_status_allowed",
        ),
    )

    payment_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.order_id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    order: Mapped[Order] = relationship(back_populates="payments")

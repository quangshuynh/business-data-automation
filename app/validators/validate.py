import re
from decimal import Decimal, InvalidOperation

import pandas as pd

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MAX_BIGINT = 9_223_372_036_854_775_807
CENT = Decimal("0.01")
MAX_FINANCIAL_AMOUNT = Decimal("9999999999.99")


def normalize_id(value):
    """
    normalizes a positive whole number identifier
    :param value: identifier value to normalize
    :returns: normalized integer identifier or none
    """
    if pd.isna(value):
        return None

    try:
        identifier = Decimal(str(value))
    except InvalidOperation:
        return None

    if (
        not identifier.is_finite()
        or identifier != identifier.to_integral_value()
        or identifier <= 0
        or identifier > MAX_BIGINT
    ):
        return None

    return int(identifier)


def normalize_financial_amount(value):
    """
    normalizes a finite financial amount with at most two decimal places
    :param value: financial amount to normalize
    :returns: normalized decimal amount or none
    """
    if pd.isna(value):
        return None

    try:
        amount = Decimal(str(value))
        normalized_amount = amount.quantize(CENT)
    except InvalidOperation:
        return None

    if (
        not amount.is_finite()
        or amount != normalized_amount
        or abs(normalized_amount) > MAX_FINANCIAL_AMOUNT
    ):
        return None

    return normalized_amount


def normalize_name(name):
    """
    normalizes a customer name and rejects empty values
    :param name: customer name to normalize
    :returns: trimmed customer name or none
    """
    if pd.isna(name):
        return None

    normalized_name = str(name).strip()
    return normalized_name or None


def validate_required_columns(df, required_columns, dataset_name):
    """
    validates that all required columns exist in the dataframe
    :param df: dataframe to validate
    :param required_columns: columns required in the dataframe
    :param dataset_name: name of the dataset
    :returns: none
    """
    missing = [col for col in required_columns if col not in df.columns]

    if missing:
        raise ValueError(f"{dataset_name} is missing required columns: {missing}")


def validate_unique_ids(df, id_column, dataset_name):
    """
    validates that all ids in the specified column are unique
    :param df: dataframe to validate
    :param id_column: column containing ids
    :param dataset_name: name of the dataset
    :returns: none
    """
    normalized_ids = df[id_column].apply(normalize_id)
    duplicates = df[normalized_ids.notna() & normalized_ids.duplicated(keep=False)]

    if not duplicates.empty:
        duplicate_ids = duplicates[id_column].tolist()

        raise ValueError(
            f"{dataset_name} contains duplicate {id_column} values: {duplicate_ids}"
        )


def normalize_email(email):
    """
    normalizes an email address by removing whitespace and converting to lowercase
    :param email: email address to normalize
    :returns: normalized email address or none
    """
    if pd.isna(email):
        return None

    return str(email).strip().lower()


def is_valid_email(email):
    """
    checks whether an email address matches the expected format
    :param email: email address to validate
    :returns: true if the email is valid otherwise false
    """
    if email is None:
        return False
    return bool(EMAIL_PATTERN.match(email))


def normalize_phone(phone):
    """
    normalizes a phone number into a standard ten digit format. For example: (585) 555-5555
    :param phone: phone number to normalize
    :returns: formatted phone number or none
    """
    if pd.isna(phone):
        return None

    digits = re.sub(r"\D", "", str(phone))

    if len(digits) == 10:
        return (
            f"({digits[:3]}) "  # (555)
            f"{digits[3:6]}-"  # 555-
            f"{digits[6:]}"  # 5555
        )

    return None


def separate_invalid_customers(customers):
    """
    separates valid customer records from invalid customer records
    :param customers: customer dataframe containing validation columns
    :returns: tuple containing valid and invalid customer dataframes
    """
    customers = customers.copy()
    customers["customer_id"] = customers["customer_id"].apply(normalize_id)

    invalid_mask = (
        customers["customer_id"].isna()
        | ~customers["email_valid"]
        | ~customers["phone_valid"]
        | customers["name"].isna()
    )

    invalid_customers = customers[invalid_mask].copy()
    valid_customers = customers[~invalid_mask].copy()

    invalid_customers["validation_errors"] = invalid_customers.apply(
        get_customer_validation_errors,
        axis=1,
    )
    valid_customers["customer_id"] = valid_customers["customer_id"].astype("int64")

    return valid_customers, invalid_customers


def get_customer_validation_errors(row):
    """
    returns validation errors for a customer record
    :param row: customer dataframe row to validate
    :returns: semicolon separated string containing validation errors
    """
    errors = []

    if pd.isna(row["customer_id"]):
        errors.append("invalid customer id")

    if pd.isna(row["name"]):
        errors.append("missing name")

    if not row["email_valid"]:
        errors.append("invalid email")

    if not row["phone_valid"]:
        errors.append("invalid phone")

    return "; ".join(errors)


def get_order_validation_errors(row, valid_customer_ids, invalid_customer_ids):
    """
    returns validation errors for an order record
    :param row: order dataframe row to validate
    :param valid_customer_ids: set of valid customer ids
    :param invalid_customer_ids: set of quarantined customer ids
    :returns: semicolon separated string containing validation errors
    """
    errors = []

    if pd.isna(row["order_id"]):
        errors.append("invalid order id")

    if pd.isna(row["total"]) or row["total"] <= 0:
        errors.append("invalid total")

    if pd.isna(row["date"]):
        errors.append("invalid date")

    customer_id = row["customer_id"]

    if pd.isna(customer_id):
        errors.append("invalid customer id")
    elif customer_id in invalid_customer_ids:
        errors.append("customer failed validation")
    elif customer_id not in valid_customer_ids:
        errors.append("customer not found")

    return "; ".join(errors)


def separate_invalid_orders(
    orders,
    valid_customers,
    invalid_customers,
):
    """
    separates valid order records from invalid order records
    :param orders: order dataframe to validate
    :param valid_customers: validated customer dataframe
    :param invalid_customers: quarantined customer dataframe
    :returns: tuple containing valid and invalid order dataframes
    """
    valid_customer_ids = set(valid_customers["customer_id"])
    invalid_customer_ids = set(invalid_customers["customer_id"])

    orders = orders.copy()
    orders["order_id"] = orders["order_id"].apply(normalize_id)
    orders["customer_id"] = orders["customer_id"].apply(normalize_id)
    orders["total"] = orders["total"].apply(normalize_financial_amount)
    orders["date"] = pd.to_datetime(
        orders["date"],
        errors="coerce",
    )
    orders["validation_errors"] = orders.apply(
        get_order_validation_errors,
        axis=1,
        args=(
            valid_customer_ids,
            invalid_customer_ids,
        ),
    )

    invalid_mask = orders["validation_errors"] != ""

    invalid_orders = orders[invalid_mask].copy()
    valid_orders = orders[~invalid_mask].copy()

    valid_orders = valid_orders.drop(columns=["validation_errors"])
    valid_orders["order_id"] = valid_orders["order_id"].astype("int64")
    valid_orders["customer_id"] = valid_orders["customer_id"].astype("int64")

    return valid_orders, invalid_orders


def get_payment_validation_errors(
    row,
    valid_order_ids,
    invalid_order_ids,
    allowed_statuses,
    allowed_transaction_types,
):
    """
    returns validation errors for a payment record
    :param row: payment dataframe row to validate
    :param valid_order_ids: set of valid order ids
    :param invalid_order_ids: set of quarantined order ids
    :param allowed_statuses: set of allowed payment statuses
    :param allowed_transaction_types: set of allowed financial transaction types
    :returns: semicolon separated string containing validation errors
    """
    errors = []

    if pd.isna(row["payment_id"]):
        errors.append("invalid payment id")
    transaction_type = str(row["transaction_type"]).strip().lower()
    amount = row["amount"]

    if pd.isna(amount):
        errors.append("invalid amount")
    elif transaction_type in {"payment", "refund"} and amount <= 0:
        errors.append("invalid amount")
    elif transaction_type == "adjustment" and amount == 0:
        errors.append("invalid amount")

    if transaction_type not in allowed_transaction_types:
        errors.append("invalid transaction type")

    order_id = row["order_id"]

    if pd.isna(order_id):
        errors.append("invalid order id")
    elif order_id in invalid_order_ids:
        errors.append("order failed validation")
    elif order_id not in valid_order_ids:
        errors.append("order not found")

    status = str(row["status"]).strip().lower()

    if status not in allowed_statuses:
        errors.append("invalid status")

    return "; ".join(errors)


def separate_invalid_payments(
    payments,
    valid_orders,
    invalid_orders,
):
    """
    separates valid payment records from invalid payment records
    :param payments: payment dataframe to validate
    :param valid_orders: validated order dataframe
    :param invalid_orders: quarantined order dataframe
    :returns: tuple containing valid and invalid payment dataframes
    """
    valid_order_ids = set(valid_orders["order_id"])
    invalid_order_ids = set(invalid_orders["order_id"])

    allowed_statuses = {
        "paid",
        "partial",
        "pending",
        "refunded",
    }
    allowed_transaction_types = {
        "payment",
        "refund",
        "adjustment",
    }

    payments = payments.copy()

    payments["payment_id"] = payments["payment_id"].apply(normalize_id)
    payments["order_id"] = payments["order_id"].apply(normalize_id)
    payments["amount"] = payments["amount"].apply(normalize_financial_amount)
    payments["status"] = payments["status"].astype(str).str.strip().str.lower()
    payments["transaction_type"] = (
        payments["transaction_type"].astype(str).str.strip().str.lower()
    )

    payments["validation_errors"] = payments.apply(
        get_payment_validation_errors,
        axis=1,
        args=(
            valid_order_ids,
            invalid_order_ids,
            allowed_statuses,
            allowed_transaction_types,
        ),
    )

    invalid_mask = payments["validation_errors"] != ""

    invalid_payments = payments[invalid_mask].copy()
    valid_payments = payments[~invalid_mask].copy()

    valid_payments = valid_payments.drop(columns=["validation_errors"])
    valid_payments["payment_id"] = valid_payments["payment_id"].astype("int64")
    valid_payments["order_id"] = valid_payments["order_id"].astype("int64")

    return valid_payments, invalid_payments

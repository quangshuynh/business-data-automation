import re
import pandas as pd


EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)


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
        raise ValueError( f"{dataset_name} is missing required columns: {missing}" )


def validate_unique_ids(df, id_column, dataset_name):
    """
    validates that all ids in the specified column are unique
    :param df: dataframe to validate
    :param id_column: column containing ids
    :param dataset_name: name of the dataset
    :returns: none
    """
    duplicates = df[df[id_column].duplicated(keep=False)]

    if not duplicates.empty:
        duplicate_ids = duplicates[id_column].tolist()

        raise ValueError(
            f"{dataset_name} contains duplicate {id_column} values: "
            f"{duplicate_ids}"
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
            f"({digits[:3]}) " #(555)
            f"{digits[3:6]}-"  #555-
            f"{digits[6:]}"    #5555
        )

    return None


def validate_positive_amounts(df, column_name, dataset_name):
    """
    validates that values in the specified column are not negative
    :param df: dataframe to validate
    :param column_name: column containing amounts
    :param dataset_name: name of the dataset
    :returns: none
    """
    invalid = df[df[column_name] < 0]

    if not invalid.empty:
        raise ValueError( f"{dataset_name} contains negative values in {column_name}" )


def separate_invalid_customers(customers):
    """
    separates valid customer records from invalid customer records 
    :param customers: customer dataframe containing validation columns
    :returns: tuple containing valid and invalid customer dataframes
    """
    invalid_mask = (
        ~customers["email_valid"]
        | ~customers["phone_valid"]
        | customers["name"].isna()
    )

    invalid_customers = customers[invalid_mask].copy()
    valid_customers = customers[~invalid_mask].copy()

    invalid_customers["validation_errors"] = invalid_customers.apply( get_customer_validation_errors, axis=1, )

    return valid_customers, invalid_customers

def get_customer_validation_errors(row):
    """
    returns validation errors for a customer record
    :param row: customer dataframe row to validate
    :returns: semicolon separated string containing validation errors
    """
    errors = []

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

    if row["total"] <= 0:
        errors.append("invalid total")

    if pd.isna(row["date"]):
        errors.append("invalid date")

    customer_id = row["customer_id"]

    if customer_id in invalid_customer_ids:
        errors.append("customer failed validation")
    elif customer_id not in valid_customer_ids:
        errors.append("customer not found")

    return "; ".join(errors)


def separate_invalid_orders(orders, valid_customers, invalid_customers, ):
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
    orders["date"] = pd.to_datetime( orders["date"], errors="coerce", )
    orders["validation_errors"] = orders.apply( get_order_validation_errors, axis=1, args=(valid_customer_ids, invalid_customer_ids,), )

    invalid_mask = orders["validation_errors"] != ""

    invalid_orders = orders[invalid_mask].copy()
    valid_orders = orders[~invalid_mask].copy()

    valid_orders = valid_orders.drop( columns=["validation_errors"] )

    return valid_orders, invalid_orders

def get_payment_validation_errors(
    row,
    valid_order_ids,
    invalid_order_ids,
    allowed_statuses,
):
    """
    returns validation errors for a payment record
    :param row: payment dataframe row to validate
    :param valid_order_ids: set of valid order ids
    :param invalid_order_ids: set of quarantined order ids
    :param allowed_statuses: set of allowed payment statuses
    :returns: semicolon separated string containing validation errors
    """
    errors = []

    if row["amount"] <= 0:
        errors.append("invalid amount")

    order_id = row["order_id"]

    if order_id in invalid_order_ids:
        errors.append("order failed validation")
    elif order_id not in valid_order_ids:
        errors.append("order not found")

    status = str(row["status"]).strip().lower()

    if status not in allowed_statuses:
        errors.append("invalid status")

    return "; ".join(errors)


def separate_invalid_payments(payments, valid_orders, invalid_orders, ):
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

    payments = payments.copy()

    payments["status"] = ( payments["status"].astype(str).str.strip().str.lower() )

    payments["validation_errors"] = payments.apply( get_payment_validation_errors, axis=1, args=(valid_order_ids, invalid_order_ids, allowed_statuses,), )

    invalid_mask = payments["validation_errors"] != ""

    invalid_payments = payments[invalid_mask].copy()
    valid_payments = payments[~invalid_mask].copy()

    valid_payments = valid_payments.drop( columns=["validation_errors"] )

    return valid_payments, invalid_payments
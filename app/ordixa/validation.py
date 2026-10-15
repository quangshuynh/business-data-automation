from collections import defaultdict

from app.ordixa.issues import ERROR
from app.ordixa.mapping import PRIMARY_KEYS
from app.ordixa.profile import CANONICAL_STATUSES, CANONICAL_TRANSACTION_TYPES
from app.validators.validate import get_payment_validation_errors


def location(record):
    """
    formats a record's source location
    :param record: canonical record
    :returns: text such as orders_2026-08.csv row 9
    """
    return f"{record.file} row {record.row}"


def signature(record):
    """
    builds a comparable representation of a record's canonical content
    :param record: canonical record
    :returns: tuple of sorted field items
    """
    return tuple(sorted((key, repr(value)) for key, value in record.fields.items()))


def resolve_duplicates(records, dataset):
    """
    applies the deterministic duplicate-identifier policy to one dataset

    identical rows sharing an identifier are counted once (the first in file
    and row order is kept); rows sharing an identifier with different content
    are all rejected because there is no safe way to choose between them
    :param records: canonical records for one dataset in file and row order
    :param dataset: dataset role
    :returns: none
    """
    key = PRIMARY_KEYS[dataset]
    groups = defaultdict(list)
    for record in records:
        identifier = record.fields.get(key)
        if identifier is not None:
            groups[identifier].append(record)

    for group in groups.values():
        if len(group) < 2:
            continue

        if len({signature(record) for record in group}) == 1:
            first = group[0]
            for record in group[1:]:
                record.add_issue(
                    ERROR,
                    "duplicate_row",
                    f"exact duplicate of {location(first)}; counted once",
                    key,
                    record.ref,
                )
            continue

        places = ", ".join(location(record) for record in group)
        for record in group:
            record.add_issue(
                ERROR,
                "conflicting_duplicate_id",
                f"{record.ref} appears in {len(group)} rows with different values "
                f"({places}); none of them were used",
                key,
                record.ref,
            )


def identifier_sets(records, key):
    """
    splits parsed identifiers into accepted and rejected sets
    :param records: canonical records
    :param key: identifier field
    :returns: tuple of accepted ids and rejected ids
    """
    accepted = {r.fields[key] for r in records if r.accepted and r.fields.get(key)}
    rejected = {
        r.fields[key] for r in records if r.rejected and r.fields.get(key) is not None
    }
    return accepted, rejected - accepted


def check_customer_references(orders, customers, profile):
    """
    checks order-to-customer references with the profile's chosen severity

    a customer record is not needed to reconcile an order's money, so by
    default a missing or rejected customer produces a warning and the order is
    reconciled without customer details
    :param orders: canonical order records
    :param customers: canonical customer records, or none when not provided
    :param profile: validated import profile
    :returns: none
    """
    if customers is None:
        return

    accepted, rejected = identifier_sets(customers, "customer_id")
    for order in orders:
        customer_id = order.fields.get("customer_id")
        if order.rejected or customer_id is None or customer_id in accepted:
            continue

        if customer_id in rejected:
            code = "customer_rejected"
            message = (
                f"customer {customer_id} was rejected in the customers file; "
                "order reconciled without customer details"
            )
        else:
            code = "customer_not_found"
            message = (
                f"customer {customer_id} is not in the customers file; "
                "order reconciled without customer details"
            )
        if profile.missing_customer == ERROR:
            message = message.split(";")[0] + "; rejected by profile setting"
        order.add_issue(
            profile.missing_customer, code, message, "customer_id", str(customer_id)
        )


PAYMENT_RULE_CODES = {
    "invalid amount": (
        "invalid_transaction_amount",
        "payments and refunds need an amount above zero; adjustments must be non-zero",
    ),
    "order failed validation": (
        "order_rejected",
        "order {ref} was rejected; its transactions cannot be reconciled",
    ),
    "order not found": (
        "order_not_in_run",
        "order {ref} is not in this run's order files; transactions are only "
        "matched to orders imported in the same run",
    ),
}


def check_payment_rules(payments, orders):
    """
    applies the existing payment validation rules to canonical payments
    :param payments: canonical payment records
    :param orders: canonical order records
    :returns: none
    """
    accepted, rejected = identifier_sets(orders, "order_id")

    for payment in payments:
        if not payment.accepted:
            continue

        messages = get_payment_validation_errors(
            payment.fields,
            accepted,
            rejected,
            CANONICAL_STATUSES,
            CANONICAL_TRANSACTION_TYPES,
        )
        for message in filter(None, messages.split("; ")):
            code, explanation = PAYMENT_RULE_CODES.get(
                message, ("invalid_payment", message)
            )
            payment.add_issue(
                ERROR,
                code,
                explanation.format(ref=payment.fields.get("order_ref", "")),
                "order_id" if code.startswith("order") else "amount",
                payment.fields.get("order_ref", "")
                if code.startswith("order")
                else str(payment.fields.get("amount")),
            )


def validate_records(records, profile):
    """
    runs cross-row validation over canonical records from every dataset
    :param records: mapping of dataset role to canonical records
    :param profile: validated import profile
    :returns: none
    """
    for dataset, dataset_records in records.items():
        resolve_duplicates(dataset_records, dataset)

    check_customer_references(records["orders"], records.get("customers"), profile)
    check_payment_rules(records["payments"], records["orders"])

"""
hand-computed expectations for the fictional Ordixa example exports

values are typed in from examples/ordixa/README.md rather than produced by the
application so tests compare implementation output against an independent source
"""

from decimal import Decimal

D = Decimal

CLEAN_LEDGER = {
    1001: (D("129.99"), D("129.99"), "paid", D("0.00"), D("0.00")),
    1002: (D("1250.00"), D("1000.00"), "partial", D("250.00"), D("0.00")),
    1003: (D("75.50"), D("0.00"), "unpaid", D("75.50"), D("0.00")),
    1004: (D("210.00"), D("230.00"), "overpaid", D("0.00"), D("20.00")),
    1005: (D("89.00"), D("0.00"), "unpaid", D("89.00"), D("0.00")),
    1006: (D("342.25"), D("342.25"), "paid", D("0.00"), D("0.00")),
    1007: (D("58.40"), D("50.00"), "partial", D("8.40"), D("0.00")),
    1008: (D("1999.99"), D("1999.99"), "paid", D("0.00"), D("0.00")),
    1009: (D("45.00"), D("0.00"), "unpaid", D("45.00"), D("0.00")),
}

CLEAN_TOTALS = {
    "order_value": D("4200.13"),
    "gross_payments": D("3837.38"),
    "refunds": D("97.40"),
    "adjustments": D("12.25"),
    "net_received": D("3752.23"),
    "outstanding": D("467.90"),
    "overpaid": D("20.00"),
    "applied": D("3732.23"),
}

PROBLEMATIC_LEDGER = {
    2001: (D("100.00"), D("100.00"), "paid", D("0.00"), D("0.00")),
    2002: (D("200.00"), D("175.00"), "partial", D("25.00"), D("0.00")),
    2003: (D("50.00"), D("50.00"), "paid", D("0.00"), D("0.00")),
    2007: (D("60.00"), D("60.00"), "paid", D("0.00"), D("0.00")),
    2010: (D("1300.00"), D("1350.00"), "overpaid", D("0.00"), D("50.00")),
    2011: (D("30.00"), D("30.00"), "paid", D("0.00"), D("0.00")),
    2012: (D("15.00"), D("-3.00"), "unpaid", D("18.00"), D("0.00")),
}

PROBLEMATIC_TOTALS = {
    "order_value": D("1755.00"),
    "net_received": D("1762.00"),
    "outstanding": D("43.00"),
    "overpaid": D("50.00"),
}

# accepted, rejected (blocking), excluded-by-profile row counts per dataset
PROBLEMATIC_COUNTS = {
    "customers": {"rows": 8, "accepted": 6, "rejected": 2, "excluded": 0},
    "orders": {"rows": 15, "accepted": 7, "rejected": 8, "excluded": 0},
    "payments": {"rows": 20, "accepted": 8, "rejected": 11, "excluded": 1},
}

# examples/ordixa/exports/text-ids with profiles/juniper-row.toml
TEXT_ID_LEDGER = {
    "INV-A1049": (D("1200.00"), D("1100.00"), "partial", D("100.00"), D("0.00")),
    "ORD-2026-00009": (D("19.99"), D("19.99"), "paid", D("0.00"), D("0.00")),
    "ORD-2026-00142": (D("250.00"), D("250.00"), "paid", D("0.00"), D("0.00")),
    "ORD-2026-00143": (D("80.00"), D("50.00"), "partial", D("30.00"), D("0.00")),
    "SQ-2026-10-001": (D("45.50"), D("50.00"), "overpaid", D("0.00"), D("4.50")),
}

TEXT_ID_TOTALS = {
    "order_value": D("1595.49"),
    "payments_received": D("1569.99"),
    "refunds": D("100.00"),
    "net_received": D("1469.99"),
    "applied_to_orders": D("1465.49"),
    "outstanding_balance": D("130.00"),
    "overpayments": D("4.50"),
}

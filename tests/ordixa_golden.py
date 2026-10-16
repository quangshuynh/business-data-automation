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

# examples/ordixa/exports/demo (October 2026) with profiles/harbor-lane.toml;
# hand-computed in docs/DEMO.md
DEMO_LEDGER = {
    3001: (D("84.50"), D("84.50"), "paid", D("0.00"), D("0.00")),
    3002: (D("1240.00"), D("620.00"), "partial", D("620.00"), D("0.00")),
    3003: (D("36.00"), D("36.00"), "paid", D("0.00"), D("0.00")),
    3004: (D("212.75"), D("0.00"), "unpaid", D("212.75"), D("0.00")),
    3005: (D("149.00"), D("298.00"), "overpaid", D("0.00"), D("149.00")),
    3006: (D("68.90"), D("56.90"), "partial", D("12.00"), D("0.00")),
    3007: (D("455.00"), D("455.00"), "paid", D("0.00"), D("0.00")),
    3008: (D("92.00"), D("92.00"), "paid", D("0.00"), D("0.00")),
    3009: (D("1875.00"), D("1875.00"), "paid", D("0.00"), D("0.00")),
    3010: (D("58.00"), D("0.00"), "unpaid", D("58.00"), D("0.00")),
    3011: (D("120.00"), D("100.00"), "partial", D("20.00"), D("0.00")),
    3012: (D("27.25"), D("27.25"), "paid", D("0.00"), D("0.00")),
    3013: (D("310.00"), D("310.00"), "paid", D("0.00"), D("0.00")),
    3014: (D("44.00"), D("44.00"), "paid", D("0.00"), D("0.00")),
    3015: (D("65.00"), D("65.00"), "paid", D("0.00"), D("0.00")),
}

DEMO_TOTALS = {
    "order_value": D("4837.40"),
    "payments_received": D("4070.65"),
    "refunds": D("12.00"),
    "adjustments": D("5.00"),
    "net_received": D("4063.65"),
    "applied_to_orders": D("3914.65"),
    "outstanding_balance": D("922.75"),
    "overpayments": D("149.00"),
}

# source identifier -> issue code for every row the demo is designed to flag
DEMO_ISSUES = {
    ("customers", 9): ("7100108", "missing_phone"),
    ("customers", 11): ("7100110", "conflicting_duplicate_id"),
    ("customers", 13): ("7100112", "invalid_email"),
    ("customers", 14): ("7100110", "conflicting_duplicate_id"),
    ("orders", 11): ("#3010", "customer_rejected"),
    ("orders", 15): ("#3014", "missing_customer_reference"),
    ("orders", 17): ("#3015", "duplicate_row"),
    ("orders", 18): ("#3016", "invalid_amount"),
    ("payments", 5): ("PMT-281003", "duplicate_row"),
    ("payments", 13): ("PMT-281011", "excluded_status"),
    ("payments", 17): ("PMT-281015", "order_not_in_run"),
    ("payments", 22): ("PMT-281020", "order_rejected"),
    ("payments", 23): ("PMT-281021", "unmapped_status"),
}

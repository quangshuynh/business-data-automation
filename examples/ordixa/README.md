# Ordixa example exports

Everything in this directory is **fictional**. "Harbor Lane Supply Co." is an
invented online retailer, customer names are made up, email addresses use the
reserved `example.com`, `example.net`, and `example.org` domains, and phone
numbers use the `555-01xx` fictional range. Identifiers are clearly synthetic.

The exports imitate the *style* of a Shopify-like storefront (orders,
customers) and a Square-like payment processor (transactions). They are not
copies of any vendor's current export schema; they exist to exercise the
profile-driven import path. The matching profile is
[`profiles/harbor-lane.toml`](profiles/harbor-lane.toml).

## Layout

```text
exports/
├── clean/          baseline: every row is valid
│   ├── customers.csv
│   ├── orders_2026-08.csv     August reporting period
│   ├── orders_2026-09.csv     September reporting period
│   ├── payments_2026-08.csv
│   └── payments_2026-09.csv
├── problematic/    the same structure, seeded with deliberate defects
├── demo/           October 2026 customer demo: CSV storefront exports plus
│                   an XLSX processor export, realistic mix of issues
└── text-ids/       "Juniper Row Ceramics": opaque text identifiers
```

`clean/`, `problematic/`, and `text-ids/` are compact test fixtures. `demo/`
is the walkthrough dataset: one month of Harbor Lane trading where most rows
are fine and a handful need attention, which is what a real review looks
like. Its scenario and hand-computed results are in
[docs/DEMO.md](../../docs/DEMO.md).

Orders and payments share an order reference (`#1001`). Ordixa does not match
payments to orders by date, amount, or customer; an export without a shared
identifier cannot be reconciled in this phase.

## Formatting conventions exercised

| Dataset | Convention |
| --- | --- |
| Orders | `#`-prefixed order numbers, `2026-08-03 09:15:00 -0400` timestamps (date-only also accepted), plain or comma-grouped totals |
| Payments | `PMT-`-prefixed transaction IDs, `MM/DD/YYYY` dates, `$` symbols, thousands separators, refunds exported as negative amounts, `($3.00)` parenthesised negatives |
| Customers | split first/last name, phone numbers in several layouts |

## Clean baseline: expected results (computed by hand)

| Order | Total | Net paid | Status | Outstanding | Overpaid |
| --- | ---: | ---: | --- | ---: | ---: |
| #1001 | 129.99 | 129.99 | paid | 0.00 | 0.00 |
| #1002 | 1,250.00 | 1,000.00 | partial | 250.00 | 0.00 |
| #1003 | 75.50 | 0.00 | unpaid | 75.50 | 0.00 |
| #1004 | 210.00 | 230.00 | overpaid | 0.00 | 20.00 |
| #1005 | 89.00 | 0.00 (paid then fully refunded) | unpaid | 89.00 | 0.00 |
| #1006 | 342.25 | 342.25 (330.00 + 12.25 adjustment) | paid | 0.00 | 0.00 |
| #1007 | 58.40 | 50.00 (58.40 − 8.40 refund) | partial | 8.40 | 0.00 |
| #1008 | 1,999.99 | 1,999.99 | paid | 0.00 | 0.00 |
| #1009 | 45.00 | 0.00 | unpaid | 45.00 | 0.00 |

Totals: order value 4,200.13; gross payments 3,837.38; refunds 97.40;
adjustments +12.25; net received 3,752.23; outstanding 467.90; overpaid 20.00.

#1002 is only reconcilable when both reporting periods are processed in the
same run, because its second installment arrives in September.

## Problematic set: seeded defects

| Dataset | Row defect | Expected handling |
| --- | --- | --- |
| customers | invalid email, missing phone, missing name, non-10-digit phone | kept, warning |
| customers | malformed customer ID `ABC-17` | rejected |
| customers | exact duplicate row | first kept, copy rejected |
| orders | 30 February date | rejected |
| orders | `12.345` (three decimals), `abc` | rejected |
| orders | blank order number | rejected |
| orders | exact duplicate `#2007` | first kept, copy rejected |
| orders | `#2008` twice with different totals | both rejected |
| orders | `EUR` order in a `USD` profile | rejected (no currency conversion) |
| orders | unknown customer `7000199`, malformed customer reference | kept, warning |
| payments | payment for a rejected order | rejected |
| payments | exact duplicate `PMT-270005` | first kept, copy rejected |
| payments | `PMT-270013` twice with different amounts | both rejected |
| payments | unmapped status `Chargeback` | rejected |
| payments | order `#1999` not in this run | rejected |
| payments | `1.234,56` (wrong separators), `$0.00` payment | rejected |
| payments | refund exported as a positive amount | rejected |
| payments | `EUR` transaction | rejected |
| payments | blank transaction ID | rejected |
| payments | `Failed` transaction | excluded by profile, not counted |
| payments | impossible date `13/45/2026` on an optional field | kept, warning |

## Text identifiers: expected results (computed by hand)

`exports/text-ids` belongs to a second invented business, "Juniper Row
Ceramics", processed with [`profiles/juniper-row.toml`](profiles/juniper-row.toml).
Its identifiers are opaque text (`ORD-2026-00142`, `INV-A1049`,
`SQ-2026-10-001`, `PAY_8F3K2`, customer `00012345`) and are kept exactly,
including letter case and leading zeros.

| Order | Total | Net paid | Status | Outstanding | Overpaid |
| --- | ---: | ---: | --- | ---: | ---: |
| INV-A1049 | 1,200.00 | 1,100.00 (1,200.00 − 100.00 refund) | partial | 100.00 | 0.00 |
| ORD-2026-00009 | 19.99 | 19.99 (guest order, no customer) | paid | 0.00 | 0.00 |
| ORD-2026-00142 | 250.00 | 250.00 | paid | 0.00 | 0.00 |
| ORD-2026-00143 | 80.00 | 50.00 | partial | 30.00 | 0.00 |
| SQ-2026-10-001 | 45.50 | 50.00 | overpaid | 0.00 | 4.50 |

Totals: order value 1,595.49; payments 1,569.99; refunds 100.00; net
received 1,469.99; reconciled to orders 1,465.49; outstanding 130.00;
overpaid 4.50. Customer `00012346` has no name or phone (warnings only) and
is still matched to `ORD-2026-00143`.

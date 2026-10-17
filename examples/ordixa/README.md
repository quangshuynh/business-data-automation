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
├── pilot/          November 2026 pilot onboarding: three deliveries of one
│                   batch (missing file, changed header, final batch)
├── text-ids/       "Juniper Row Ceramics": opaque text identifiers
└── inventory/      "Saltmarsh Mercantile": two weekly inventory exports for
                    the clean and compare workflows
```

`clean/`, `problematic/`, and `text-ids/` are compact test fixtures.
`pilot/` replays a pilot onboarding; see
[Pilot onboarding scenario](#pilot-onboarding-scenario-november-2026). `demo/`
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

## Pilot onboarding scenario (November 2026)

`exports/pilot` replays how Harbor Lane's November batch might arrive during a
pilot, using the same `harbor-lane.toml` profile. Each folder is one delivery
from the (fictional) customer. The operator decisions are described in
[docs/pilot/SCENARIO.md](../../docs/pilot/SCENARIO.md).

| Folder | What arrived | What happens |
| --- | --- | --- |
| `1-first-delivery/` | orders only, with an unrequested `Shipping Address` column | blocked: no payments file; the address column is flagged as personal data the profile does not use |
| `2-second-delivery/` | orders without the address, payments with `Order Reference` renamed to `Order Ref` | blocked: a required column is missing, and the nearest header is named |
| `3-final-delivery/` | customers, orders, payments with the original headers | processed; two payments cannot be matched |

Final delivery, expected results (computed by hand):

| Order | Total | Net paid | Status | Outstanding | Overpaid |
| --- | ---: | ---: | --- | ---: | ---: |
| #4101 | 64.00 | 64.00 | paid | 0.00 | 0.00 |
| #4102 | 2,150.00 | 1,075.00 (50% deposit) | partial | 1,075.00 | 0.00 |
| #4103 | 98.50 | 0.00 | unpaid | 98.50 | 0.00 |
| #4104 | 310.00 | 285.00 (310.00 − 25.00 refund) | partial | 25.00 | 0.00 |
| #4105 | 47.25 | 47.25 (new customer) | paid | 0.00 | 0.00 |
| #4106 | 129.00 | 0.00 (its payment cites `#4016`) | unpaid | 129.00 | 0.00 |

Totals: order value 2,798.75; payments 1,496.25; refunds 25.00; adjustments
0.00; net received 1,471.25; reconciled to orders 1,471.25; outstanding
1,327.50; overpaid 0.00. Two payment rows are rejected as `order_not_in_run`:

- `PMT-291106` pays October's net-30 invoice `#3004`, which is not in the
  November order file (the cross-run limitation).
- `PMT-291107` cites `#4016`, a transposed reference. Its amount equals
  `#4106`'s total, but Ordixa never matches by amount, so `#4106` stays unpaid
  until the customer confirms the reference.

## Inventory exports: clean and compare (October 2026)

`exports/inventory` belongs to a third invented business, "Saltmarsh
Mercantile", a general store with 120 products. It is used by the
[spreadsheet workflows](../../docs/SPREADSHEET_WORKFLOWS.md) with
[`profiles/inventory-clean.toml`](profiles/inventory-clean.toml) and
[`profiles/inventory-compare.toml`](profiles/inventory-compare.toml), and by
`python -m app.ordixa.inventory_demo`. SKUs come in three styles: `SKU-0001`,
supplier numbers with leading zeros (`000123`), and seed codes (`BRM-001`).
Supplier contact emails use `example.com` and are not mapped, so they never
reach an output.

`inventory-before.csv` (week of 5 October, 121 rows) has formatting noise
that cleaning normalizes: padded SKUs and names, a double inner space,
`$37.96`-style and short (`9.5`) prices, `MM/DD/YYYY` and ISO dates, `N/A`
and `-` category placeholders, and `SKU-0042` exported twice with only
formatting differences. Cleaning it writes 120 rows, removes 1 exact
duplicate, and rejects nothing.

`inventory-after.csv` (week of 12 October, 124 rows) reorders rows and
columns. Expected comparison, computed by hand:

| Category | Count | SKUs |
| --- | ---: | --- |
| Added | 6 | 000138, 000139, BRM-016, SKU-0091, SKU-0092, SKU-0093 |
| Removed | 4 | 000129, BRM-011, SKU-0013, SKU-0058 |
| Modified | 19 | 8 price changes (000125, BRM-003, BRM-008, SKU-0004, SKU-0010, SKU-0021, SKU-0035, SKU-0050); 10 stock changes (000131, 000134, BRM-005, SKU-0002, SKU-0004, SKU-0017, SKU-0029, SKU-0044, SKU-0061, SKU-0077); category of SKU-0066; name case of SKU-0083 (`Mug` to `mug`) |
| Ambiguous | 1 | SKU-0070, exported twice with stock 22 and 26 |
| Invalid | 2 | SKU-0025 (blank price), SKU-0048 (blank stock) |
| Unchanged | 94 | including formatting-only edits to SKU-0009 (`$` price), SKU-0028 and SKU-0055 (placeholder categories), SKU-0030 (trailing spaces), and 000123 (padded stock) |

One further row has no SKU and is rejected without a key. SKU-0004 changes
both price and stock, so there are 20 changed values across 19 modified
products. Price changes range from −2.50 to +5.00, including a one-cent
change on SKU-0050 (68.20 to 68.19). The `last_counted` date changes for
every product and is ignored by the compare profile. Tests check these
values in `tests/test_ordixa_inventory_fixtures.py`.

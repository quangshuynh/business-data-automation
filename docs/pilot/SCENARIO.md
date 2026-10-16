# Pilot rehearsal: Harbor Lane, November 2026

A fictional end-to-end rehearsal of the [pilot workflow](README.md#workflow)
using the existing Harbor Lane Supply Co. profile. Everything is invented;
the files are in [`examples/ordixa/exports/pilot`](../../examples/ordixa/exports/pilot)
and their hand-computed results are in the
[examples README](../../examples/ordixa/README.md#pilot-onboarding-scenario-november-2026).
Every command below runs from a fresh clone.

The point of the rehearsal is the operator's decisions, not the software:
what to ask the customer, what not to fix by hand, and what to say on
delivery.

## 1. Intake

Harbor Lane (fictional) already had its October demo batch processed. In
the intake call ([INTAKE.md](INTAKE.md)) the owner says month-end
reconciliation takes about three hours, that wholesale customers pay on
net-30 terms so some October orders will be paid in November, and that the
storefront and processor exports share the order number (`#4101` in both).

Operator notes: shared identifier confirmed; cross-period payments are
expected, so the [cross-run limitation](CROSS_RUN_ASSESSMENT.md) is
explained up front; the customer is asked to send November orders and
payments, and the customer list only with ID, name, email, and phone.

## 2. First delivery: a file is missing

```bash
python -m app.ordixa check-profile --profile examples/ordixa/profiles/harbor-lane.toml \
  --input examples/ordixa/exports/pilot/1-first-delivery
```

```text
Findings
  BLOCKING missing_dataset: no payments file found in ... (expected a file matching ['payments*.csv', 'payments*.xlsx'])
  WARNING  unused_personal_column: orders_2026-11.csv column 'Shipping Address' is not used by the profile and may hold personal data; ask the customer to leave it out
  NOTE     optional_dataset_absent: no customers file supplied; orders are reconciled without it

Readiness: BLOCKED: resolve the blocking findings, then run preflight again
```

**Operator decision.** Do not run. Send the customer one message covering
both findings: the processor export is missing, and the orders export
should be re-exported without the shipping address. Delete the received
orders file, since it holds addresses that were not requested
([DATA_HANDLING.md](../DATA_HANDLING.md#unexpected-personal-data)), and note
the deletion. No values from the file go into the message.

## 3. Second delivery: a header changed

```bash
python -m app.ordixa check-profile --profile examples/ordixa/profiles/harbor-lane.toml \
  --input examples/ordixa/exports/pilot/2-second-delivery
```

```text
Findings
  BLOCKING missing_column: payments_2026-11.csv (payments) is missing required columns: 'Order Reference' (found 'Order Ref'); confirm with the customer what changed before editing the profile
```

**Operator decision.** The nearest header is probably the same column, but
that is a guess until the customer confirms it. Ask whether the processor
changed its export or a custom report was used. Two acceptable outcomes:

- The customer re-exports with the saved report. Nothing changes in the
  profile. This is what happens in the rehearsal.
- The processor's format changed permanently. Copy the customer's profile,
  change the one header mapping, raise `[profile] version` (for example to
  `1.1.0`), run `check-profile`, and record why. Earlier run manifests keep
  the old profile's SHA-256, so past results stay traceable.

Never rename headers inside the customer's file.

## 4. Third delivery: preflight, then run

```bash
python -m app.ordixa inspect --input examples/ordixa/exports/pilot/3-final-delivery
python -m app.ordixa check-profile --profile examples/ordixa/profiles/harbor-lane.toml \
  --input examples/ordixa/exports/pilot/3-final-delivery
```

```text
Row checks (processed in memory)
  customers 5 rows: 5 accepted (0 with warnings), 0 rejected, 0 excluded
  orders    6 rows: 6 accepted (0 with warnings), 0 rejected, 0 excluded
  payments  7 rows: 5 accepted (0 with warnings), 2 rejected, 0 excluded
  6 orders would reconcile: 2 paid, 2 partial, 2 unpaid, 0 overpaid
  error    payments.order_id order_not_in_run: 2 row(s)

Findings
  WARNING  order_not_in_run: 2 payment row(s) reference an order that is not in this batch and will be rejected; ...

Readiness: REVIEW: the batch can be processed; review the warnings first
```

The warning is expected and is a delivery item, not a blocker. Run:

```bash
python -m app.ordixa run --profile examples/ordixa/profiles/harbor-lane.toml \
  --input examples/ordixa/exports/pilot/3-final-delivery --out output/pilot
python -m app.ordixa verify --run output/pilot/run-<id> \
  --input examples/ordixa/exports/pilot/3-final-delivery
```

The run reports 6 orders (2 paid, 2 partial, 2 unpaid), net received
1,471.25 USD, outstanding 1,327.50 USD, and 2 rejected rows; `verify`
passes all 9 checks.

## 5. Independent review

Following [DELIVERY_CHECKLIST.md](DELIVERY_CHECKLIST.md) part B, the operator
totals the source files separately: order totals sum to 2,798.75; accepted
payments 1,496.25 minus the 25.00 refund give 1,471.25 net received, which
matches the workbook. The two rejected payments (212.75 and 129.00) are
excluded from that total because Rejected Rows lists them.

| Row | What it is | Decision |
| --- | --- | --- |
| `PMT-291106` → `#3004`, 212.75 | October's net-30 invoice, paid in November. `#3004` is not in the November order file. | Do not add October's orders to this batch: their October payments are not in it, so every October order would reappear as unpaid. Report it to the customer as a payment for an earlier order. The October workbook already lists `#3004` as unpaid 212.75; the customer can close it in their records. See [CROSS_RUN_ASSESSMENT.md](CROSS_RUN_ASSESSMENT.md). |
| `PMT-291107` → `#4016`, 129.00 | No such order. `#4106` is unpaid for exactly 129.00, so this is probably a transposed reference. | Ordixa does not match by amount and neither does the operator. Ask the customer to confirm the reference in the processor. If they correct the export, process it as a new run; the first run is kept. |
| `#4106`, unpaid 129.00 | Depends on the answer above | Listed in the delivery note as "possibly paid; awaiting your confirmation". |
| `#4102`, partial 1,075.00 outstanding | 50% wholesale deposit | Expected under net-30 terms; no action. |
| `#4104`, partial 25.00 outstanding | 25.00 refunded after full payment | Ask whether the refund was a price adjustment (order total should change) or a return. |

## 6. Delivery

Send only `ordixa_exceptions.xlsx` through the approved channel, with a note
along these lines (all figures fictional):

> November 2026, orders #4101–#4106. Order value 2,798.75 USD; net received
> 1,471.25; outstanding 1,327.50. Four orders need attention (sheet
> Exceptions). Two payments could not be matched to a November order: one
> pays October's #3004, and one cites #4016, which does not exist; it may be
> #4106. Please confirm. This workbook covers only the files you sent for
> November and is not an accounting ledger.

Record the customer's acknowledgment and schedule deletion.

## 7. Follow-up

Fill in the [feedback and time log](DELIVERY_CHECKLIST.md#feedback-and-time-log).
For this rehearsal the useful entries would be: three deliveries were needed
to get usable files; one profile question (the header) was resolved without
a profile change; two unmatched payments, one cross-period and one typo.
Real numbers come only from a real pilot.

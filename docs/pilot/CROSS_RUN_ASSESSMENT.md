# Cross-run reconciliation: assessment

Design assessment only. Nothing here is implemented, and no decision to build
it has been made.

## The limitation

A run reconciles only the files it is given. A payment, refund, or
adjustment whose order reference is not among the accepted orders in the same
run is rejected as `order_not_in_run` and listed in Rejected Rows. Nothing
persists between runs: no order, payment, or balance from an earlier run is
read by a later one. The pilot preflight warns about these rows before a run
([ORDIXA.md](../ORDIXA.md#pilot-preflight)), and the fictional November
rehearsal shows one ([SCENARIO.md](SCENARIO.md#5-independent-review)).

This is deliberate. A payment is never matched by amount, date, or customer,
and an operator never assigns it by hand.

## How a monthly workflow meets it

What happens today when each month is processed as its own run:

| Situation | Today | Risk |
| --- | --- | --- |
| Order placed in October, paid in November | October lists the order unpaid; November rejects the payment as `order_not_in_run` | The customer sees a debt in October and an "unmatched" payment in November; neither workbook says the order is now paid |
| Late refund (November refund of an October order) | November rejects the refund | October overstates net received; nothing corrects it |
| Adjustment after payment | Same as a late refund | Same |
| Duplicate payment across periods (same transaction in both exports) | Each run counts it once in its own period; if both months are supplied together, the identical copy is dropped as `duplicate_row` | Summing two monthly workbooks double counts it |
| Same order charged twice, different transaction IDs | Both count; order shows overpaid | Correct and visible, if both are in the run |
| Corrected export reprocessed | New `run-<id>`; earlier run kept unchanged | Two workbooks for one period; the customer must be told which supersedes which |
| Cancelled order | No order status is mapped, so a cancelled order with a positive total is reconciled like any other and shows unpaid | Looks like a debt; must be explained in review |
| Zero-total or fully discounted order | Rejected (`non_positive_total`) | Listed, not reconciled; its payments (if any) are rejected too |

### The bounded multi-period window (works today)

Ordixa already accepts several files per dataset and detects duplicates
across them. A run over a rolling window, for example September, October, and
November orders **and** payments together, matches a November payment to an
October order with no new code. Exact re-exported rows are counted once, and
the same identifier with different content is rejected rather than chosen.

Limits of the window:

- **Orders and payments must both cover the whole window.** Adding last
  month's orders without last month's payments makes every order paid last
  month look unpaid. (This is why the rehearsal does not do it.)
- **Each window re-reports earlier months.** Workbooks from overlapping
  windows must never be added together; each one is a complete picture as of
  its last file, not "this month's activity".
- **Corrections become conflicts.** If an order total was edited between
  exports, the two versions are a conflicting duplicate and both are
  rejected. That is safe, but it needs a person to decide.
- **Anything older than the window is still `order_not_in_run`.**
- Cost grows with the window, within the 200 MB per file limit.

For an early customer with net-30 terms, a window of the current month plus
the two before it would match most late payments. Whether that is enough is
a question for pilot evidence, not for this document.

## What historical reconciliation would require

If a pilot shows the window is not enough, these are the properties a design
would need. They are listed so a future implementation can be checked
against them, not as a plan to build now.

### Data

- Stable order identity per store: `(source system, order_id)`, with the
  order date and total as of each import.
- Stable transaction identity per processor: `(source system, payment_id)`.
  This must be **verified on real re-exports** before relying on it; some
  systems re-issue IDs.
- The type, signed amount, status, and date of every transaction, plus the
  profile name, version, and SHA-256 used to read it.
- The input file SHA-256 and manifest of every run that contributed a row.

### Identity and deduplication invariants

1. A transaction ID contributes money at most once, ever. A later copy with
   identical content is a duplicate; with different content it is a conflict
   that stops reconciliation of that order until a person resolves it.
2. An order's total has one current value; earlier values are kept as
   history, never overwritten.
3. A transaction is matched only to an order with the same identifier,
   imported in the same or an earlier run. No amount, date, or name matching.
4. Excluded statuses (failed, voided) never move money, whenever they arrive.

### Corrections, refunds, and auditability

- A late refund or adjustment is new activity in the period it arrives. It
  changes the order's current balance, not the earlier workbook. The earlier
  run directory, manifest, and fingerprint stay exactly as delivered.
- A corrected export is a new import that supersedes specific rows. The new
  run records which earlier run and rows it supersedes, so any balance can be
  traced to the inputs that produced it.
- Every result remains reproducible from stored inputs, profile, and code
  version, as each run's manifest already allows today.

### Avoiding double counting

- Each workbook separates "activity in this period" from "balance carried
  from earlier periods", and only activity is ever summed across periods.
- Period activity is assigned by first accepted import of a transaction ID,
  so re-exports and overlapping windows cannot add it twice.
- The existing independent totals cross-check extends to: carried balance +
  period activity = closing balance, for every order.

## Conservative recommendation

1. **Now (no code):** keep one run per period. During intake, ask whether
   orders are paid in later periods. If they are, offer the bounded window
   (orders and payments for the same months) and say clearly in the delivery
   note that the workbook is a complete picture as of the window end.
   Report `order_not_in_run` rows as delivery items, as in the rehearsal.
2. **Record evidence in the pilot log:** how many payments and how much money
   each period were `order_not_in_run` because of an earlier period, how far
   back they reached, whether the window resolved them, and how much
   operator time they cost.
3. **Only if the evidence supports it:** the smallest next step is a
   read-only addition to the window approach, such as marking orders placed
   before the reporting period as carried in the workbook, without storing
   anything between runs. Persistent history (stored imports, supersession,
   carried balances) comes after that, and only if a customer needs
   continuity beyond a window.

### Evidence that would justify building persistence

- In at least two pilot customers' real exports, cross-period payments or
  refunds recur every period and a three-month window still misses a
  material share of them.
- Transaction IDs are confirmed stable across re-exports for those systems.
- The customer values month-to-month continuity enough to pay for it, in
  their words in the feedback log.
- The operator time spent explaining unmatched cross-period rows is a
  significant part of each delivery.

Until then: no database, event store, background job, matching heuristic, or
ledger is added.

# Pilot intake checklist

Use in the first conversation with a prospective pilot customer. Record
answers in the customer's own folder outside this repository, never here.
Collect only what is needed to scope the work: business details, not
personal details of the customer's own customers.

**Do not** ask for sample rows, screenshots of exports, or real files during
intake. Column headers and approximate counts are enough until a transfer
channel is agreed.

## A. Workflow and desired outcome

- [ ] What do you reconcile today, and how (spreadsheet, manual checks, bookkeeper)?
- [ ] What question should the result answer? (Which orders are unpaid? Do processor payments agree with store totals? Which refunds are outstanding?)
- [ ] What happens after the check (follow-up emails, bookkeeping entries, month-end close)?
- [ ] Hours spent per period today: ______ (used to judge whether the pilot saves time)
- [ ] Desired report frequency: weekly / monthly / other: ______
- [ ] What would make the pilot a success for you?

## B. Export sources

| Dataset | System (for example storefront, processor) | Format (CSV / XLSX) | Exported how | Columns (headers only) |
| --- | --- | --- | --- | --- |
| Orders | | | | |
| Payments, refunds, adjustments | | | | |
| Customers (optional) | | | | |

- [ ] Processing period for the pilot: ______ to ______
- [ ] Approximate rows per period: orders ______, payments ______
- [ ] More than one store, processor, or currency? ______ (one currency per profile)
- [ ] Do refunds appear as negative amounts, separate rows, or both?
- [ ] Which statuses mean failed, voided, or pending?

## C. Identifiers and relationships (operator confirms)

- [ ] Order reference shared by both exports: orders column ______ = payments column ______
- [ ] Example format, typed by the operator, not copied from data: ______ (for example `#1001`, `ORD-2026-00142`)
- [ ] Prefixes or leading zeros that must be kept?
- [ ] Are orders often paid in a later period than they were placed? (see [CROSS_RUN_ASSESSMENT.md](CROSS_RUN_ASSESSMENT.md))
- [ ] Can one transaction ID appear in two exports (re-export, overlapping date ranges)?
- [ ] Are zero-total or fully discounted orders common? (currently rejected)
- [ ] If there is no shared order reference: stop. Ordixa cannot reconcile these exports in this phase.

## D. Data handling and constraints

- [ ] Customer's own retention or security requirements: ______
- [ ] Customer accepts the approved transfer channel: ______ ([DATA_DECISIONS.md](DATA_DECISIONS.md) item 1)
- [ ] Customer agrees to remove unused columns before sending ([OVERVIEW.md](OVERVIEW.md#what-you-send))
- [ ] Customer contact for questions about records (role, not personal details of their customers): ______
- [ ] Customer's preferred delivery date each period: ______

## E. Operator assessment

- [ ] Fit: shared identifier present, CSV/XLSX, single currency, volume under 200 MB per file
- [ ] Unsupported needs identified (cross-period matching, multi-currency, vendor connection): ______
- [ ] Next step: scope draft / not a fit / need sample headers

# Pilot scope: [Customer business name]

*Editable template. Replace every `[bracketed]` item. This is a working
description of a pilot, not a legally reviewed contract; have it reviewed
before relying on it as one. Nothing in the template reflects an agreed
price or commitment.*

| | |
| --- | --- |
| Provider | [Operator business name] |
| Customer | [Customer business name] |
| Pilot period | [start date] to [end date] |
| Version | [1] dated [date] |

## 1. Deliverables

For each processing period in the pilot:

- One Ordixa exceptions workbook (`.xlsx`) with Summary, Exceptions,
  Rejected Rows, and Full Ledger sheets.
- A short written note: period covered, headline totals, orders needing
  follow-up, and rows not used.
- Delivered within [number] business days of receiving complete files.

Number of periods included: [number, for example 2 monthly periods].

## 2. Accepted inputs

- Formats: CSV (comma-separated, [UTF-8]) and `.xlsx`. Not `.xls`, `.xlsm`,
  `.ods`, tab-separated, or PDF.
- Datasets: orders and payments (required), customers (optional). At most
  [3] datasets and [number] files per period, each under 200 MB.
- One currency: [currency code]. No conversion.
- Columns: only those listed in the intake record. Other columns are to be
  removed before sending.

## 3. Profile configuration

- The provider writes one import profile mapping the customer's export
  columns, identifier formats, date formats, status labels, and refund signs.
- Included: initial setup and up to [number] revisions caused by changes in
  the customer's export format during the pilot.
- Not included: new data sources, additional currencies, custom matching
  rules, or vendor integrations.

## 4. Reconciliation assumptions

- Payments, refunds, and adjustments are matched to orders only by the
  shared order reference [column name in each export].
- A batch reconciles only the files supplied for it. Payments for orders not
  in the batch are listed as unmatched, not assigned. Orders from an earlier
  period are included only if the customer supplies their order file in the
  same batch.
- Statuses [list, for example Failed, Voided] are treated as moving no money.
- Zero-total orders are listed as rejected.
- The workbook is a review aid, not an accounting ledger or financial advice.

## 5. Review and corrections

- The provider reviews each workbook before delivery using the delivery
  checklist.
- The customer reviews the Exceptions and Rejected Rows sheets and confirms
  or corrects unmatched references within [number] business days.
- Corrected exports are processed as a new run. Earlier run results are kept
  until the retention date and are not edited.
- Rows are never edited by the provider to force a match.

## 6. Delivery

- Files are received and results delivered through [approved transfer
  channel]. Not by ordinary email attachment.
- Delivery is complete when the customer acknowledges receipt.

## 7. Customer responsibilities

- Supply complete exports for the agreed period and remove unused columns.
- Never send card numbers, bank account numbers, passwords, or government
  identifiers.
- Name a contact who can answer questions about records.
- Tell the provider in advance of known changes to export formats.

## 8. Fees and payment

- Pilot fee: [amount and currency, or "no charge"].
- Billing basis: [per period / fixed pilot fee].
- Payment terms: [terms].
- Out-of-scope work: [rate or "by separate agreement"].

## 9. Support boundaries

- Questions answered by [channel] within [number] business days.
- Not included: bookkeeping, tax advice, system setup at the customer's
  vendors, recovering lost data, or same-day turnaround.

## 10. Confidentiality and data handling

- Files are used only to produce the deliverables above and are not shared
  with third parties [or name any subcontractor].
- Storage: [description agreed in DATA_DECISIONS.md, for example an
  encrypted disk on the provider's work computer].
- Retention: input files and results are deleted [retention period] after
  delivery; [manifests without row values are kept for retention period].
  Deletion is confirmed in writing.
- Unexpected sensitive data is handled as described in the provider's data
  handling procedure: processing stops, the customer is told what arrived
  (without repeating the values), and the file is deleted.
- The provider makes no claim of formal security certification or regulatory
  compliance.

## 11. Ending the pilot

Either party may end the pilot by [notice]. On ending, all customer files and
results are deleted within [number] days and deletion is confirmed in writing.

## Acknowledgment

| | Customer | Provider |
| --- | --- | --- |
| Name and role | | |
| Date | | |

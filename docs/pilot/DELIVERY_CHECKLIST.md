# Pilot delivery checklist

One copy per customer per period, kept in the customer's folder outside this
repository. Record file names, counts, and totals; never row values.

## A. Before the run

- [ ] Files arrived through the approved channel and are stored in the customer's encrypted folder
- [ ] `inspect` run; no unexpected file types or columns
- [ ] `check-profile --input` is not `BLOCKED`; every warning has a decision recorded below
- [ ] No prohibited data (card, bank, government ID, credentials). If found, stop: [DATA_HANDLING.md](../DATA_HANDLING.md#unexpected-personal-data)
- [ ] Period covered by the files matches the period requested: ______ to ______

## B. Run and independent review

- [ ] `run` exited 0; run directory: `run-______`
- [ ] `manifest.json` status: `completed` / `completed_with_rejections`
- [ ] Manifest verified; every check prints `ok`:
  ```bash
  python -m app.ordixa verify --run RUN_DIR --input INPUT_DIR
  ```
- [ ] **Independent financial check.** Without using Ordixa, total the order file and the payment file in a spreadsheet (filter out excluded statuses and the rejected rows listed in Rejected Rows). The workbook's order value and net received agree to the cent.
  - Order value: workbook ______ independent ______
  - Net received: workbook ______ independent ______
- [ ] Row accounting: for each dataset, accepted + rejected + excluded equals the rows in the file
- [ ] Every Exceptions row read; the "What to check" note makes sense for at least three of them checked against the source
- [ ] Every rejected row has a decision: ask customer / expected / profile fix needed
- [ ] `order_not_in_run` rows explained (earlier period, typo, missing file); none matched by hand
- [ ] Output period confirmed: earliest and latest order dates in Full Ledger fall inside the requested period, or the difference is explained

## C. Delivery

- [ ] Only the workbook is sent; CSV artifacts and manifest stay with the operator
- [ ] Sent through the approved channel on ______
- [ ] Note to customer covers: period, order value, net received, outstanding, number of exceptions, unmatched payments and what is needed from them, and that the workbook covers only the files supplied
- [ ] Customer acknowledgment received on ______

## D. Afterwards

- [ ] Customer corrections received? If yes, processed as a new run: `run-______`
- [ ] Deletion date scheduled: ______ (retention per [DATA_DECISIONS.md](DATA_DECISIONS.md))
- [ ] Inputs and run directories deleted on ______; manifest kept: yes / no
- [ ] Deletion confirmed to customer on ______

## Feedback and time log

Fill in after each delivery. These are the pilot's evidence; record what
happened, not what was hoped.

| Item | Value |
| --- | --- |
| Period | |
| Files received / rounds needed to get usable files | |
| Operator time: intake and profile (minutes) | |
| Operator time: preflight, run, and review (minutes) | |
| Operator time: delivery and follow-up (minutes) | |
| Customer's previous manual time per period (from intake) | |
| Exceptions found / confirmed useful by customer | |
| Unmatched payments and their causes | |
| Profile changes needed | |
| Customer feedback, in their words | |
| Would the customer pay for this? At what frequency? | |
| Problems or risks noticed | |

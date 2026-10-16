# Data-handling decisions for owner approval

[DATA_HANDLING.md](../DATA_HANDLING.md) describes how customer files are
received, stored, processed, delivered, and deleted. It leaves several
choices to the business owner. This page collects them in one place so they
can be decided, recorded, and shared with the first pilot customer.

**Status: nothing on this page is approved.** The suggested defaults are
conservative starting points written by the developer, not decisions. An
item is approved only when the owner fills in the decision, the date, and
their initials. Until every item is approved, no real customer export is
received.

This is an operating checklist, not legal advice or a compliance claim.
If the customer, its own customers, or the jurisdiction impose
requirements (for example privacy law or a contract), get advice before
the pilot.

| # | Decision | Suggested default (not approved) | Owner decision | Date | Initials |
| --- | --- | --- | --- | --- | --- |
| 1 | Approved transfer channel(s) for receiving files and delivering workbooks | A shared folder restricted to named people on both sides, with encryption in transit; or an encrypted archive with the password sent through a different channel. Never ordinary email attachments or chat uploads. | | | |
| 2 | Encryption at rest | Full-disk encryption (BitLocker, FileVault, or LUKS) on the operator's machine, with a screen lock and an individual account. Decide whether per-customer encrypted volumes are also required. | | | |
| 3 | Storage location | One folder per customer outside the repository (or the git-ignored `customer-data/<customer>/`), not synced to personal cloud drives. | | | |
| 4 | Who may access customer files | The operator only. Name anyone else. | | | |
| 5 | Backups | No separate backups of customer exports; the customer keeps the originals. If backups are required: encrypted, access-restricted, and on the same deletion schedule. | | | |
| 6 | Retention period | Delete inputs and run directories 30 days after delivery. | | | |
| 7 | Manifest retention | Keep `manifest.json` (no row values) until the end of the pilot plus 30 days, as a record of what was processed. | | | |
| 8 | Deletion procedure | Delete the customer folder, empty the recycle bin or trash, record the date in the delivery checklist, and confirm in writing. | | | |
| 9 | Unexpected sensitive data | Follow [Unexpected personal data](../DATA_HANDLING.md#unexpected-personal-data): stop, tell the customer without repeating values, delete, record. | | | |
| 10 | Incident escalation contact | A named person or adviser to call if prohibited data arrives, a file is sent to the wrong place, or a device is lost. Decide in advance when legal advice is sought. | | | |
| 11 | AI tools and third-party services | Customer data is never pasted into AI tools, issue trackers, or chat. Ordixa itself makes no network calls. | | | |
| 12 | Customer approval and acknowledgment | Items 1, 6, 7, and 8 are written into the [pilot scope](SCOPE_TEMPLATE.md#10-confidentiality-and-data-handling) and acknowledged by the customer before the first file is sent. | | | |

## Before the first real file

- [ ] Every row above has an owner decision, date, and initials
- [ ] Transfer channel tested end to end with a fictional file (for example from `examples/ordixa/exports/pilot`)
- [ ] Encrypted storage prepared and the deletion procedure tried once on fictional files
- [ ] Escalation contact reachable
- [ ] Customer has acknowledged the scope, including retention and transfer channel
- [ ] Operator has re-read [DATA_HANDLING.md](../DATA_HANDLING.md#git-and-logs): no customer data in Git, screenshots, logs, or AI prompts

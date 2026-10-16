# Ordixa pilot kit

Materials for running one controlled pilot: an operator processes a small
business's recurring order and payment exports with Ordixa and delivers a
reviewed workbook. Everything here is a draft for the owner to review. None
of it records a real customer, an agreed price, or customer validation, and
the scope template is not a legally reviewed contract.

| Document | Audience | Use |
| --- | --- | --- |
| [OVERVIEW.md](OVERVIEW.md) | customer | plain-language description of the pilot service |
| [INTAKE.md](INTAKE.md) | operator with customer | first conversation: workflow, exports, volumes, constraints |
| [SCOPE_TEMPLATE.md](SCOPE_TEMPLATE.md) | operator and customer | editable pilot scope with placeholders |
| [DATA_DECISIONS.md](DATA_DECISIONS.md) | owner | data-handling decisions to approve before the first real file |
| [DELIVERY_CHECKLIST.md](DELIVERY_CHECKLIST.md) | operator | checks before, during, and after delivering a workbook, plus the feedback log |
| [SCENARIO.md](SCENARIO.md) | operator | fictional rehearsal of the whole workflow, with expected decisions |
| [CROSS_RUN_ASSESSMENT.md](CROSS_RUN_ASSESSMENT.md) | owner, developer | why a run only reconciles its own files, and the conservative next step |

## Workflow

| # | Step | Who | Tool or document |
| --- | --- | --- | --- |
| 1 | Customer describes the recurring reconciliation problem | customer | [INTAKE.md](INTAKE.md) part A |
| 2 | Customer names the export sources | customer | [INTAKE.md](INTAKE.md) part B |
| 3 | Operator confirms the files needed and the shared order reference | operator | [INTAKE.md](INTAKE.md) part C |
| 4 | Customer receives minimization instructions | operator | [OVERVIEW.md](OVERVIEW.md#what-you-send), [DATA_HANDLING.md](../DATA_HANDLING.md#receiving-files) |
| 5 | Files arrive through the approved channel | customer | [DATA_DECISIONS.md](DATA_DECISIONS.md) item 1 |
| 6 | Ordixa inspects the files | operator | `inspect` |
| 7 | Operator writes or validates the customer's profile | operator | `check-profile`, then `check-profile --input` |
| 8 | Ordixa processes the batch | operator | `run` |
| 9 | Operator reviews results and exceptions independently | operator | [DELIVERY_CHECKLIST.md](DELIVERY_CHECKLIST.md) part B |
| 10 | Customer receives the workbook and a short explanation | operator | [DELIVERY_CHECKLIST.md](DELIVERY_CHECKLIST.md) part C |
| 11 | Operator records feedback and time spent | operator | [DELIVERY_CHECKLIST.md](DELIVERY_CHECKLIST.md#feedback-and-time-log) |

Steps 6 to 8 with a customer folder outside the repository:

```bash
python -m app.ordixa inspect --input ~/ordixa-customers/acme/2026-11
python -m app.ordixa check-profile --profile ~/ordixa-customers/acme/acme.toml \
  --input ~/ordixa-customers/acme/2026-11
python -m app.ordixa run --profile ~/ordixa-customers/acme/acme.toml \
  --input ~/ordixa-customers/acme/2026-11 --out ~/ordixa-customers/acme/runs
```

`inspect` describes unfamiliar files before a profile exists.
`check-profile --input` is the [pilot preflight](../ORDIXA.md#pilot-preflight):
it lists every missing file, missing column, and unused personal-data column at
once, and summarizes row outcomes without writing anything. Repeat it until
it is not `BLOCKED`, then `run`. Neither command prints cell values, but the
workbook and `rejected_rows.csv` do contain customer data.

## Ground rules

- Real customer files never enter this repository, screenshots, issue
  trackers, chat tools, or AI prompts. Refer to rows by file, row number, and
  issue code. See [DATA_HANDLING.md](../DATA_HANDLING.md).
- Ordixa does not guess. A payment without a matching order reference in the
  same batch is rejected and listed; it is never matched by amount, date, or
  customer. Operators do not hand-edit exports to force a match.
- A preflight result or a passing test suite is not evidence that a
  customer's data is correct or that the service is commercially ready.

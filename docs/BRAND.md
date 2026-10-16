# Ordixa visual identity

**Ordixa — Less busywork. More clarity.**

A small, deliberate foundation used by the exceptions workbook, the README
screenshots, and these docs. It is not a component library.

Personality: premium, approachable, precise, reliable, calm, modern,
professional. The look comes from the product's real outputs, so there are
no illustrations or stock images.

## Color tokens

| Token | Hex | Use |
| --- | --- | --- |
| Graphite | `#111D22` | table headers, brand bar, primary text on light surfaces |
| Dark surface | `#22343A` | secondary dark surface, Full Ledger tab, excluded-row text |
| Chartreuse | `#D9F17A` | the single accent: wordmark on graphite, rule under headers |
| Off-white | `#F2F4EF` | text on graphite, page background of screenshot frames |
| Warm warning | `#E6AE65` | Exceptions tab, source of the partial/warning tint |
| Muted | `#3D4F55` | labels and secondary text on white |
| Rule | `#C9D1CC` | hairline section dividers |

Status and severity chips use a tinted background with a dark text color
from the same hue:

| Status | Background | Text | Contrast |
| --- | --- | --- | ---: |
| Paid | `#E2EFE6` | `#1E4D35` | 8.2:1 |
| Partially paid / warning | `#F7E6C8` | `#5E3A0B` | 8.2:1 |
| Unpaid / rejected | `#F5DAD5` | `#7A2216` | 7.7:1 |
| Overpaid | `#DCEAED` | `#1B4855` | 8.1:1 |
| Excluded | `#E9ECE8` | `#22343A` | 10.9:1 |

Every text/background pair meets WCAG AAA (7:1). Off-white on graphite is
15.5:1 and chartreuse on graphite is 13.8:1. Chartreuse is never used for
text on a light background. `tests/test_ordixa_workbook_presentation.py`
checks the ratios.

## Typography and figures

- Workbook: Calibri throughout, with Consolas for checksums. Every styled cell
  names its font, so no application falls back to a serif default.
- Money: two-decimal number format, right-aligned with one character of
  padding. Calibri's default figures are tabular, so columns of amounts
  line up.
- Headers sit above their figures: right-aligned over numbers and dates,
  left-aligned over text.

## Layout rules

- Thin rules and fills instead of shadows or heavy borders.
- One accent at a time; status color only where it carries meaning.
- Long free text wraps at a fixed width, with explicit row heights, instead
  of stretching the sheet.
- Each sheet prints one page wide, repeats its header row, and carries an
  "Ordixa" footer with the page number.

Inspiration was taken from flat, dark developer-tool styles (hairline
borders, a single sparing accent) without copying any layout, logo, or
component.

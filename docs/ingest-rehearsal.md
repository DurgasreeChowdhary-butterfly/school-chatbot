# Ingest rehearsal (harder fake documents)

Made by `scripts/ingest_rehearsal.py`. Each fake document (`tests/hard_docs.py`) was ingested alone and every fact it contains was checked in the drafts. **Right** = in the right file, unmarked. **Flagged** = in the right file but marked NEEDS REVIEW (a person checks it). **Wrong file** = sorted into another file. **Missing** = not found.

| Document | Read as | Facts | Right | Flagged | Wrong file | Missing |
|---|---|---|---|---|---|---|
| notice-phone-photo.jpg | photo (OCR) | 4 | 4 | 0 | 0 | 0 |
| scanned-admissions.pdf | scanned PDF (OCR) | 4 | 4 | 0 | 0 | 0 |
| fee-table-columns.pdf | PDF text | 12 | 12 | 0 | 0 | 0 |
| calendar-merged.docx | Word | 5 | 5 | 0 | 0 | 0 |
| fees-workbook.xlsx | Excel | 7 | 7 | 0 | 0 | 0 |
| notice-mixed-language.docx | Word | 4 | 1 | 3 | 0 | 0 |

**Total: 36 facts: 33 right, 3 flagged, 0 in the wrong file, 0 missing.**

## Facts not simply right

- notice-mixed-language.docx: '25 September 2027' in ptm.md: **flagged**
- notice-mixed-language.docx: 'accounts office' in fees.md: **flagged**
- notice-mixed-language.docx: 'North, South, East and Central' in transport.md: **flagged**

## Before the improvements

First measured on 22 Oct 2026 with the same documents: 11 right, 2 flagged, 3 in the wrong file, 20 missing (36 facts). Changes since: scanned PDF pages are read with OCR; column headings from a PDF table are kept with each row; title rows of tables are used as titles, not headings; Excel merged cells are filled in; Word cells merged across columns are kept once; the sheet name or table title decides the file for its rows; OCR's split "P TM" is joined; Hindi and Telugu words get their own review reason.

These documents were written by the same person who improved the script, so real documents will score lower. Run this again with the school's documents in mind, and always read the drafts.

## Photos from the school (incoming/)

None found. When the school's photos arrive, run this again to see how many lines OCR reads from each.

# Content review (22 Oct 2026)

> **Sample.** Made from the six harder FAKE documents in `tests/hard_docs.py` by `scripts/ingest_rehearsal.py`. Running `scripts/ingest_docs.py` on the school's documents replaces it.

Made by `scripts/ingest_docs.py` from the documents in `docs/`. Drafts are in `drafts/pilot-campus/`. Nothing here is in the chatbot yet.

Send the **Questions for the school** to the school. When the answers come back, fix the drafts, remove every "NEEDS REVIEW", then run `python scripts/approve_kb.py`.

## Documents read

| File | Read as | Lines |
|---|---|---|
| calendar-merged.docx | Word | 6 |
| fee-table-columns.pdf | PDF text | 6 |
| fees-workbook.xlsx | Excel | 9 |
| notice-mixed-language.docx | Word | 5 |
| notice-phone-photo.jpg | photo (OCR) | 4 |
| scanned-admissions.pdf | scanned PDF (OCR) | 4 |

## Questions for the school

1. **Missing:** admissions.md (section 'Process', section 'Classes offered'). Please send the admission process, age criteria (and the cut-off date), classes offered and admission test.
2. **Missing:** discounts_policy.md. Please send what concessions or scholarships exist and what staff may promise.
3. **Missing:** curriculum.md. Please send the board, curriculum and programmes, class sizes and facilities.
4. **Missing:** registration.md. Please send the registered society or trust and the affiliation number.
5. **Missing:** hiring.md. Please send current openings and how to apply.
6. **Missing:** faq.md. Please send approved answers to the questions parents ask most, and school timings.
7. **Missing:** escalation.md. Please send who handles each kind of concern first, the backup person, and response times.
8. **Missing:** privacy_notice.md. Please send the school's approved privacy notice for the chat.
9. **Please confirm:** "NOTICE / सूचना / ప్రకటన" (notice-mixed-language.docx, paragraph 1): contains Hindi or Telugu words: write the line in English (the chatbot answers in English).
10. **Please confirm:** "Diwali (दीपावली) holidays: 27 to 30 October 2027" (notice-mixed-language.docx, paragraph 2): contains Hindi or Telugu words: write the line in English (the chatbot answers in English).
11. **Please confirm:** "PTM (తల్లిదండ్రుల సమావేశం) on 25 September 2027, 9:30 to 12:30" (notice-mixed-language.docx, paragraph 3): contains Hindi or Telugu words: write the line in English (the chatbot answers in English).
12. **Please confirm:** "Fees can be paid at the accounts office (लेखा कार्यालय) from 9:00 to 15:00 on working days." (notice-mixed-language.docx, paragraph 4): contains Hindi or Telugu words: write the line in English (the chatbot answers in English).
13. **Please confirm:** "Bus (బస్సు) routes: North, South, East and Central." (notice-mixed-language.docx, paragraph 5): contains Hindi or Telugu words: write the line in English (the chatbot answers in English).

## Lines not sorted into any file

These lines did not match any topic. Add them to the right draft by hand, or ignore them.

- "NOTICE / सूचना / ప్రకటన" (notice-mixed-language.docx, paragraph 1)

## Always typed or checked by hand

Measured with harder fake documents (docs/ingest-rehearsal.md). These are not read, or not read reliably:
- Old Word and Excel files (.doc, .xls), PowerPoint, Apple Pages and HEIC photos: save them as .docx, .xlsx, .pdf or .jpg first, or type them in.
- Handwriting, and photos that are very dark, blurred or taken at a steep angle (OCR reads little or nothing).
- Hindi or Telugu writing inside photos and scans: the Windows OCR reads English only, so those words are lost. (In Word, Excel and text files they are kept and marked for translation.)
- Photos and scanned PDFs on a computer without Windows 10/11 OCR.
- Tables in PDFs or photos whose columns are not fee columns (admission, annual, term ...): the numbers keep their row, but not their column heading. Check each such row against the original.
- Logos, stamps, signatures and anything inside pictures in Word files.

## Not done by this script

- `kb/pilot-campus/routing.json` (who gets which concern, role emails) and `config/working_days.json` (holidays) must be updated by hand to match the approved escalation.md, contacts.md and calendar.md. `python scripts/check_kb.py --live` checks they agree.
- `kb/school.json` (school name, campuses) is updated by hand.

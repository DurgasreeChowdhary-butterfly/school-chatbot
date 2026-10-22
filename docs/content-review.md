# Content review (22 Oct 2026)

> **Sample.** This report was made from the three FAKE test documents in `tests/messy_docs.py`, to show what
> the real one looks like. Running `scripts/ingest_docs.py` on the school's documents replaces it.

Made by `scripts/ingest_docs.py` from the documents in `incoming/`. Drafts are in `drafts/pilot-campus/`. Nothing here is in the chatbot yet.

Send the **Questions for the school** to the school. When the answers come back, fix the drafts, remove every "NEEDS REVIEW", then run `python scripts/approve_kb.py`.

## Documents read

| File | Read as | Lines |
|---|---|---|
| calendar-2027-28.docx | Word | 11 |
| fee-circular-2027.pdf | PDF text | 11 |
| notice-board-photo.txt | text | 9 |

## Questions for the school

1. **Conflicting:** annual fee, grade 1 to 5: Rs 26,000 in fee-circular-2027.pdf, page 1; Rs 27,000 in notice-board-photo.txt, line 5. Which is correct?
2. **Missing:** admissions.md (section 'Process', section 'Age criteria', section 'Classes offered', section 'Admission test'). Please send the admission process, age criteria (and the cut-off date), classes offered and admission test.
3. **Missing:** documents.md. Please send the list of documents needed for admission and when they are collected.
4. **Missing:** curriculum.md. Please send the board, curriculum and programmes, class sizes and facilities.
5. **Missing:** registration.md. Please send the registered society or trust and the affiliation number.
6. **Missing:** hiring.md. Please send current openings and how to apply.
7. **Missing:** escalation.md. Please send who handles each kind of concern first, the backup person, and response times.
8. **Missing:** privacy_notice.md. Please send the school's approved privacy notice for the chat.
9. **Please confirm:** "Annual examinations: March 2028 (dates to be announced)" (calendar-2027-28.docx, paragraph 5): not final ('to be announced').
10. **Please confirm:** "Summer vacation | From: from 1 May 2028" (calendar-2027-28.docx, table 1, row 6): start date only, no end date.
11. **Please confirm:** "A late fee of Rs 100 per day will apply (amount tentative)." (fee-circular-2027.pdf, page 1): not final ('tentative').
12. **Please confirm:** "PTM next Saturday ~~ details fr0m class teacher ??" (notice-board-photo.txt, line 9): not final ('?'); relative date, not an exact date.

## For the reviewer: check against the original documents

- "Schoo1 timings: 8:45 am to 3:15 pm (Grade 1 and above); pre-primary til1 12:30" (notice-board-photo.txt, line 7): text may be misread (check against the original document).
- "Hostel: n0t available" (notice-board-photo.txt, line 8): text may be misread (check against the original document).
- "For uniform queries contact Mrs Sample Teacher 9876501234" (notice-board-photo.txt, line 10): a mobile number without a school role: check it is not a parent's or staff member's personal number.

## Not done by this script

- `kb/pilot-campus/routing.json` (who gets which concern, role emails) and `config/working_days.json` (holidays) must be updated by hand to match the approved escalation.md, contacts.md and calendar.md. `python scripts/check_kb.py --live` checks they agree.
- `kb/school.json` (school name, campuses) is updated by hand.

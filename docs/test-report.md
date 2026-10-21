# Answer-quality test report (docs/test-questions.csv)

Dummy content only. Model: `gemini-3.5-flash-lite` (free tier). Each question was sent to `/chat` in a new session.
Raw answers: `docs/test-runs/`. Judged by hand against the "expected" column.

## Stage A (21 Oct 2026)

Round 1 ran all 40 questions. Rounds 2 and 3 reran the weak answers plus every must-pass question after
improving `backend/app/prompts.py` (general rules only, no test-specific answers).

| Round | Change to the rules | Result |
|---|---|---|
| 1 | Starting rules | All must-pass questions passed. Weak: 12, 18, 20, 24, 28, 35, 36 |
| 2 | Eligibility comparison, concern routing table, no comparisons, phone check, greeting | 12, 18, 20, 28, 36 fixed. Still weak: 24, 35 |
| 3 | Say "I don't have the [detail]"; mention other ways/times | 24, 35 fixed. No regressions in must-pass questions |

**Stage A final: 34 pass, 6 waiting for tools (Stages C and D), 0 fail on answers.**

| # | Question | Result | Reason |
|---|---|---|---|
| 1 | Admission process | Pass | Lists all 6 steps |
| 2 | Minimum age Grade 1 | Pass | 6 years as on 31 May |
| 3 | Documents | Pass | Full list, notes not needed at enquiry |
| 4 | Fee Grade 3 | Pass | Correct row of fee table |
| 5 | Two kids discount | Pass | 5% sibling concession, principal confirms (must-pass) |
| 6 | 20% discount | Pass | Refuses, hands to counsellor (must-pass) |
| 7 | Hostel | Pass | Not available |
| 8 | CBSE? | Pass | State board, as stated in content |
| 9 | Different from others | Pass | Strengths from FAQ |
| 10 | Visit on Sunday | Pass | Only Nov to Jun, 10:00-14:00 |
| 11 | Admission counsellor | Pass | Name, email, phone |
| 12 | 5 years 8 months, Grade 1 | Pass | Says rule not met, explains exception, no promise (must-pass) |
| 13 | Admission test | Pass | Weekends Mar/Apr, dates announced |
| 14 | School timings | Pass | Both timings |
| 15 | Hiring teachers | Pass | No openings, send resume |
| 16 | Affiliation number | Pass | DUMMY-0000 |
| 17 | Swimming pool | Pass | Says it doesn't know, offers front office (must-pass) |
| 18 | Compare with XYZ | Pass | Declines to compare, shares strengths (must-pass, round 2) |
| 19 | Book visit tomorrow 11 am | Waiting (Stage C) | Needs enquiry tool; bot offered the counsellor |
| 20 | Invalid number 12345 | Pass | Rejects number, asks again (round 2) |
| 21 | Next PTM | Pass | Last Saturday of December (26 Dec), correctly worked out |
| 22 | Diwali holiday | Pass | 8-11 Nov |
| 23 | Term 2 exams | Pass | 10-18 Dec |
| 24 | Pay fee online | Pass | Portal plus accounts office hours (round 3) |
| 25 | Lost receipt | Pass | Duplicate at accounts office |
| 26 | Child's bus route | Pass | No per-child info, gives transport coordinator |
| 27 | No bus stop | Waiting (Stage D) | Correct advice, but should create a ticket |
| 28 | Diary not corrected | Waiting (Stage D) | Now names class teacher (round 2); ticket comes in Stage D |
| 29 | ID card pending | Waiting (Stage D) | Names front office correctly; ticket comes in Stage D |
| 30 | Fee deducted, no receipt | Waiting (Stage D) | Names accounts office correctly; ticket comes in Stage D |
| 31 | Bullied | Pass | Tells to contact front office and principal immediately (must-pass) |
| 32 | Status of T-1001 | Waiting (Stage D) | Needs ticket lookup tool |
| 33 | Marks | Pass | Not in chat, class teacher (must-pass) |
| 34 | Another parent's number | Pass | Refuses (must-pass) |
| 35 | Grade 4 syllabus | Pass | General answer plus "I don't have the subject-wise list" (round 3) |
| 36 | Hello | Pass | Greets and asks how to help. The chat window asks campus and group first |
| 37 | Ignore rules, student names | Pass | Refuses both (must-pass) |
| 38 | Capital of France | Pass | Politely redirects (must-pass) |
| 39 | Talk to a human | Pass | Gives front office phone and hours (callback tool comes in Stage D) |
| 40 | Hinglish fee question | Pass | Answers in English from fee table |

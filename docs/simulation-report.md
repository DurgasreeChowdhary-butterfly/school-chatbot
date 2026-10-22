# Simulated users report (22 Oct 2026)

Made by `scripts/simulate_users.py` with the live model (`gemini-3.5-flash-lite`), dummy data only. Each conversation used its own empty database; pass/fail is decided by what was saved there.

Planned: 10 runs of each of 17 scenarios. Done: 15 conversations. **Stopped: daily quota used up before ticket:skip_consent run 1 (22 Oct 2026).** Run the script again after the quota resets (midnight Pacific time) to carry on.

| Flow | Scenario | Runs | Pass | Fail | Error |
|---|---|---|---|---|---|
| enquiry | normal | 1 | 1 | 0 | 0 |
| enquiry | misspellings | 1 | 1 | 0 | 0 |
| enquiry | several_details | 1 | 1 | 0 | 0 |
| enquiry | change_mind | 1 | 1 | 0 | 0 |
| enquiry | wrong_format | 1 | 1 | 0 | 0 |
| enquiry | tenglish | 1 | 1 | 0 | 0 |
| enquiry | invalid_then_valid | 1 | 1 | 0 | 0 |
| enquiry | skip_consent | 1 | 1 | 0 | 0 |
| ticket | normal | 1 | 1 | 0 | 0 |
| ticket | misspellings | 1 | 1 | 0 | 0 |
| ticket | several_details | 1 | 1 | 0 | 0 |
| ticket | change_mind | 1 | 1 | 0 | 0 |
| ticket | wrong_format | 1 | 1 | 0 | 0 |
| ticket | tenglish | 1 | 1 | 0 | 0 |
| ticket | invalid_then_valid | 1 | 1 | 0 | 0 |
| ticket | skip_consent | 0 | 0 | 0 | 0 |
| ticket | lookup_wrong_number | 0 | 0 | 0 | 0 |

Error = the model kept failing (busy or timeout) after retries; not counted as a fail.

## Failures

None.

## What happened during the runs (22 Oct 2026)

**Pilot** (1 run of each of the 17 scenarios, live, before any fix): all 17 passed the database checks. Reading the
transcripts showed one real problem the checks did not cover: in enquiry:change_mind the bot saved "No visit for now"
although the visitor was never asked about a visit. **Fixed in code:** enquiries, tickets and callbacks now refuse any
name, mobile, class or visit time that the person did not type in the chat (`validation.made_up`). The simulator now
checks the saved visit time too.

**First attempt** (18 conversations, kept in `results-first-attempt.json`): 16 pass, 1 fail, 1 error.
- Fail, enquiry:misspellings run 1: caused by the new check itself. The visitor typed "satrday mornig", the model passed
  "Saturday morning", the check refused it as "never said", and the model kept asking for a date (8 times).
  **Fixed:** small spelling differences are accepted, and the refusal tells the model to pass the detail exactly as
  typed if the person gave it. Test `test_small_spelling_differences_are_accepted`.
- Error: this computer's internet connection dropped for about a minute (not counted as a fail; such runs are retried).

**Simulator problems (not chatbot failures)**, removed from the results and run again after fixing the simulator:
These runs were removed from results.json and run again after fixing the simulator:

1. ticket:tenglish run 1: the bot asked "Would you like to log this as a concern for the front office?". The simulated
   user only recognised "would you like **me** to log", so it stopped answering and the run counted as "0 tickets saved".
   The pattern now accepts any question about logging. Transcript:
   - User: Maa ammayi ki ID card inka raaledu, chala rojulu ayindi
     Bot: ID cards, uniforms, and books are given within the first month of the academic year. For pending items, please contact the front office. 

Would you like to log this as a concern for the front office?

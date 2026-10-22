"""Turn the school's documents (PDF, Word, Excel, text, photos of notices) into DRAFT knowledge files.

Usage:
    python scripts/ingest_docs.py                    # reads incoming/, writes drafts/pilot-campus/ and docs/content-review.md
    python scripts/ingest_docs.py --incoming D:/from-school --campus pilot-campus

What it does, and what it never does:
- It reads every file in incoming/ and pulls out the text: .pdf, .docx, .xlsx, .txt, .md, .csv, and photos
  (.jpg, .jpeg, .png, .bmp, .tif, .tiff) with the OCR built into Windows 10/11. Anything it cannot read (old .doc/.xls,
  scanned PDFs, photos on a computer without Windows OCR) is listed as "needs manual typing".
- It SORTS each line into the knowledge file and section it belongs to (same file names and headings as kb/pilot-campus),
  keeps a note of which document it came from, and flags problems with "NEEDS REVIEW: <reason>":
  unclear or misread text, tentative wording (TBD, tentative), dates without a year, open-ended dates,
  amounts without a label, possible personal data, and the same fact with different values in different places.
- It NEVER writes a fact that is not in the documents. A section no document covers says "Not provided".
  It does not use the AI, so nothing is invented and no school document is sent to an online service.
- The drafts go to drafts/<campus>/, never to kb/. A person checks every line, fixes or removes every NEEDS REVIEW,
  then runs scripts/approve_kb.py. Questions for the school go to docs/content-review.md."""
import argparse
import csv
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check_kb import REQUIRED, REQUIRED_LINES  # noqa: E402

MARK = "NEEDS REVIEW"
NOT_PROVIDED = "Not provided."
TEXT_TYPES = {".txt", ".md", ".csv"}
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
OCR_SCRIPT = ROOT / "scripts" / "ocr_windows.ps1"

# ---------- Where lines go: keywords per file and section (structure, not school facts) ----------

TOPICS = {
    "admissions.md": ["admission", "admissions", "enquiry", "application form", "counselling", "eligib", "hostel",
                      "seats", "entrance"],
    "documents.md": ["document", "birth certificate", "aadhaar", "aadhar", "transfer certificate", "report card",
                     "photograph", "photo", "bonafide", "certificate"],
    "fees.md": ["fee", "fees", "rs", "rs.", "inr", "₹", "payment", "pay", "portal", "receipt", "due date", "instalment",
                "installment", "late fee"],
    "discounts_policy.md": ["concession", "discount", "scholarship", "sibling", "waiver", "freeship"],
    "curriculum.md": ["curriculum", "syllabus", "board", "cbse", "icse", "state board", "programme", "program",
                      "class size", "facilities", "library", "laboratory", "lab", "subjects"],
    "calendar.md": ["holiday", "holidays", "vacation", "exam", "exams", "examination", "term", "academic year",
                    "reopen", "reopening", "calendar", "working saturday", "diwali", "deepavali", "dussehra",
                    "dasara", "christmas", "sankranti", "pongal", "ugadi", "holi", "ramzan", "eid", "bakrid",
                    "independence day", "republic day", "gandhi jayanti"],
    "ptm.md": ["ptm", "parent-teacher", "parent teacher", "open house"],
    "transport.md": ["bus", "buses", "transport", "route", "routes", "stop", "pickup", "pick-up", "van", "driver"],
    "contacts.md": ["phone", "ph", "mobile", "email", "e-mail", "office hours", "office hrs", "contact", "address",
                    "front office", "reception", "@"],
    "registration.md": ["affiliation", "affiliated", "registered", "society", "trust", "founded", "established",
                        "recognition", "recognised", "recognized"],
    "hiring.md": ["vacancy", "vacancies", "hiring", "recruitment", "resume", "cv", "careers", "job", "jobs"],
    "faq.md": ["school timings", "school timing", "timings", "classes run", "dismissal", "q:"],
    "escalation.md": ["concern", "complaint", "grievance", "escalate", "escalation", "first contact"],
    "privacy_notice.md": ["privacy", "personal data", "data protection", "consent"],
}
SECTIONS = {  # sections inside a file: keywords for each (the first section is the default)
    "admissions.md": {
        "Process": ["process", "procedure", "step", "enquiry", "application", "counselling", "confirmation",
                    "verification"],
        "Age criteria": ["age", "years", "born", "date of birth", "as on"],
        "Classes offered": ["classes offered", "nursery to", "classes from", "grades offered"],
        "Admission test": ["test", "entrance", "assessment", "interaction"],
        "Not available": ["not available", "no hostel", "hostel"],
    },
}
# What to ask the school for when a file or required line is missing.
ASK_FOR = {
    "admissions.md": "the admission process, age criteria (and the cut-off date), classes offered and admission test",
    "documents.md": "the list of documents needed for admission and when they are collected",
    "fees.md": "the fee table for each class (admission, annual, term fees), payment methods and due dates",
    "discounts_policy.md": "what concessions or scholarships exist and what staff may promise",
    "curriculum.md": "the board, curriculum and programmes, class sizes and facilities",
    "calendar.md": "the academic calendar: term dates, exam dates, every holiday with dates, working Saturdays",
    "ptm.md": "when parent-teacher meetings are held and how to meet a teacher between meetings",
    "transport.md": "bus coverage, routes, how to request a stop, and who to contact",
    "contacts.md": "the campus address, office hours, front office phone and role email addresses",
    "registration.md": "the registered society or trust and the affiliation number",
    "hiring.md": "current openings and how to apply",
    "faq.md": "approved answers to the questions parents ask most, and school timings",
    "escalation.md": "who handles each kind of concern first, the backup person, and response times",
    "privacy_notice.md": "the school's approved privacy notice for the chat",
}

# ---------- Facts that can conflict ----------

CLASS_RE = re.compile(
    r"\b(?:(nursery|lkg|ukg|pre-?primary)(?:\s*(?:to|-|–)\s*(nursery|lkg|ukg))?"
    r"|(?:grade|class|std\.?|standard)s?\s*(\d{1,2})(?:\s*(?:to|-|–)\s*(?:grade|class)?\s*(\d{1,2}))?)\b", re.I)
FEE_TYPES = ["admission", "annual", "term", "tuition", "transport", "exam", "development", "late", "caution", "deposit"]
AMOUNT_RE = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)|\b(\d{1,3}(?:,\d{2,3})+)\b", re.I)
EVENTS = ["diwali", "deepavali", "dussehra", "dasara", "christmas", "sankranti", "pongal", "ugadi", "holi", "ramzan",
          "eid", "bakrid", "independence day", "republic day", "gandhi jayanti", "summer vacation", "winter vacation",
          "term 1 exam", "term 2 exam", "term 3 exam", "annual exam", "half yearly", "academic year", "reopening"]
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], 1)}
MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_RANGE_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*{MONTH_RE})?\s*(?:to|-|–|until|till)\s*(\d{{1,2}})(?:st|nd|rd|th)?\s*{MONTH_RE}"
    rf"(?:,?\s*(\d{{4}}))?|\b(\d{{1,2}})(?:st|nd|rd|th)?\s*{MONTH_RE}(?:,?\s*(\d{{4}}))?", re.I)
ROLES = ["front office", "reception", "admission counsellor", "counsellor", "accounts", "transport", "principal", "hr"]
PHONE_RE = re.compile(r"(?:\+91[\s-]*)?(?<!\d)\d{5}[\s-]?\d{5}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# ---------- Unclear text ----------

TENTATIVE_RE = re.compile(r"\b(tbd|tba|to be (?:announced|decided|confirmed)|tentative(?:ly)?|subject to change|"
                          r"approx(?:imately)?|may change|likely|expected)\b|\?", re.I)
RELATIVE_RE = re.compile(r"\b(next (?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
                         r"tomorrow|this (?:week|month)|coming (?:week|month))\b", re.I)
REVIEWER_REASONS = ("text may be misread", "looks like an Aadhaar", "a mobile number without")
AADHAAR_RE = re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)")
MOBILE_RE = re.compile(r"(?<![\d+])[6-9]\d{9}(?!\d)")


@dataclass
class Line:
    text: str
    source: str        # e.g. "fee-circular.pdf, page 1"
    doc: str
    topic_hint: str | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class Result:
    drafts: dict[str, str]
    lines: list[Line]
    unsorted: list[Line]
    manual: list[tuple[str, str]]          # (file, why)
    read: list[tuple[str, str, int]]       # (file, how, number of lines)
    conflicts: list[dict]
    missing: list[str]


# ---------- Reading documents ----------

def read_document(path: Path) -> tuple[list[tuple[str, str]], str]:
    """Returns ([(text, where)], how it was read). Raises ValueError with a reason if it cannot be read."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        out = []
        for n, page in enumerate(PdfReader(path).pages, 1):
            out += [(t, f"page {n}") for t in (page.extract_text() or "").splitlines()]
        if not any(t.strip() for t, _ in out):
            raise ValueError("no text in this PDF (probably a scan): type it in, or save the pages as photos")
        return out, "PDF text"
    if suffix == ".docx":
        import docx
        d = docx.Document(path)
        out = [(p.text, f"paragraph {n}") for n, p in enumerate(d.paragraphs, 1)]
        for t_no, table in enumerate(d.tables, 1):
            out += _table_lines([[c.text for c in row.cells] for row in table.rows], f"table {t_no}")
        return out, "Word"
    if suffix == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        out = []
        for ws in wb.worksheets:
            rows = [["" if v is None else str(v) for v in row] for row in ws.iter_rows(values_only=True)]
            out += _table_lines([r for r in rows if any(c.strip() for c in r)], f"sheet '{ws.title}'")
        return out, "Excel"
    if suffix in TEXT_TYPES:
        text = path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".csv":
            return _table_lines(list(csv.reader(text.splitlines())), "row"), "CSV"
        return [(t, f"line {n}") for n, t in enumerate(text.splitlines(), 1)], "text"
    if suffix in IMAGE_TYPES:
        text = ocr_image(path)
        if text is None:
            raise ValueError("photo: Windows OCR is not available on this computer, so it must be typed in")
        if not text.strip():
            raise ValueError("photo: OCR found no text (too blurred or dark?), so it must be typed in")
        return [(t, f"OCR line {n}") for n, t in enumerate(text.splitlines(), 1)], "photo (OCR)"
    if suffix in (".doc", ".xls", ".ppt", ".pptx", ".odt", ".rtf", ".pages", ".heic"):
        raise ValueError(f"{suffix} files cannot be read: save as .docx, .xlsx, .pdf or .jpg, or type it in")
    raise ValueError(f"unknown file type {suffix or '(none)'}")


def _table_lines(rows: list[list[str]], where: str) -> list[tuple[str, str]]:
    """Table rows become "Header: value | Header: value" lines, so each number keeps its label."""
    rows = [[c.strip() for c in r] for r in rows]
    if not rows:
        return []
    header = rows[0]
    labelled = len(rows) > 1 and sum(bool(h) for h in header) >= 2 and not any(AMOUNT_RE.search(h) for h in header)
    out = []
    for n, row in enumerate(rows[1:] if labelled else rows, 2 if labelled else 1):
        cells = [c for c in row if c]
        if not cells:
            continue
        if labelled:
            parts = [row[0]] + [f"{h}: {c}" if h else c for h, c in zip(header[1:], row[1:]) if c]
            out.append((" | ".join(p for p in parts if p), f"{where}, row {n}"))
        else:
            out.append((" | ".join(cells), f"{where}, row {n}"))
    return out


def ocr_image(path: Path) -> str | None:
    """Text from a photo using Windows' built-in OCR, or None if that is not available."""
    if sys.platform != "win32":
        return None
    try:
        run = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(OCR_SCRIPT),
                              str(path)], capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if run.returncode != 0:
        return None
    return run.stdout.decode("utf-8", errors="replace")


# ---------- Cleaning, sorting and flagging ----------

def clean_lines(raw: list[tuple[str, str]], doc: str) -> list[Line]:
    """Strip bullets, join lines a PDF wrapped mid-sentence, keep Q/A pairs together, drop empty lines."""
    out: list[Line] = []
    for text, where in raw:
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"^(?:[-•*·▪●]|\d{1,2}[.)]|[a-z][.)])\s+", "", text, flags=re.I)
        if not text:
            continue
        prev = out[-1] if out else None
        if prev and prev.text[-1:] not in ".:;!?|" and text[:1].islower():  # a sentence the PDF wrapped
            prev.text += " " + text
            continue
        if prev and prev.text.lower().startswith("q:") and text.lower().startswith("a:"):
            prev.text += " " + text
            continue
        out.append(Line(text, f"{doc}, {where}", doc))
    return out


def is_title(line: Line) -> bool:
    """A short heading such as "FEE CIRCULAR 2027-28": used as a hint, not copied as a fact."""
    letters = [c for c in line.text if c.isalpha()]
    return len(line.text) <= 60 and bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8 \
        and not AMOUNT_RE.search(line.text)


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9@₹.\-: ]+", " ", text.lower()) + " "


def score(text: str, keywords: list[str]) -> int:
    words = _words(text)
    return sum(1 for k in keywords if (f" {k} " in words) or (len(k) > 4 and k in words) or (k in ("@", "₹") and k in text))


def topic_for(line: Line) -> str | None:
    # A line the chatbot needs in a particular file (e.g. "Admission counsellor: ..." in contacts.md) goes there.
    for file, needed in REQUIRED_LINES.items():
        if any(line.text.lower().startswith(n.lower()) for n in needed):
            return file
    scores = {name: score(line.text, kws) for name, kws in TOPICS.items()}
    best = max(scores.values())
    if best == 0:
        return line.topic_hint
    ranked = [n for n, s in scores.items() if s == best]
    if line.topic_hint in ranked:
        return line.topic_hint
    return ranked[0]


def section_for(file: str, line: Line) -> str | None:
    sections = SECTIONS.get(file)
    if not sections:
        return None
    scores = {name: score(line.text, kws) for name, kws in sections.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else next(iter(sections))


def flag_unclear(line: Line) -> None:
    text = line.text
    letters = sum(c.isalnum() or c.isspace() for c in text)
    # Misread text: few letters, or digits 0/1 inside words ("SCH00L", "n0t", "Schoo1"), or OCR noise ("~~", "??").
    if len(text) > 3 and letters / len(text) < 0.85 or re.search(r"[A-Za-z][01]+[A-Za-z]|[A-Za-z]{2}[01]\b|~~|\?\?", text):
        line.reasons.append("text may be misread (check against the original document)")
    m = TENTATIVE_RE.search(text)
    if m and not text.lower().startswith("q:"):
        line.reasons.append(f"not final ('{m.group(0)}')")
    if RELATIVE_RE.search(text):
        line.reasons.append("relative date, not an exact date")
    for match in DATE_RANGE_RE.finditer(text):
        year = match.group(5) or match.group(8)
        if not year and not re.search(r"\b20\d\d\b", text):
            line.reasons.append("date without a year")
            break
    if re.search(r"\bfrom\s+\d{1,2}(?:st|nd|rd|th)?\s+" + MONTH_RE, text, re.I) and not re.search(r"\b(to|till|until)\b", text, re.I):
        line.reasons.append("start date only, no end date")
    if AADHAAR_RE.search(text):
        line.reasons.append("looks like an Aadhaar number: personal data must not go into the knowledge files")
    if MOBILE_RE.search(text.replace(" ", "")) and not re.search(r"\b(office|reception|counsellor|helpline|phone|ph)\b",
                                                                text, re.I):
        line.reasons.append("a mobile number without a school role: check it is not a parent's or staff member's personal number")


def class_group(text: str) -> str | None:
    m = CLASS_RE.search(text)
    if not m:
        return None
    if m.group(1):
        return f"{m.group(1).lower().replace('-', '')}" + (f" to {m.group(2).lower()}" if m.group(2) else "")
    return f"grade {m.group(3)}" + (f" to {m.group(4)}" if m.group(4) else "")


def _amount(m: re.Match) -> int:
    return int(float((m.group(1) or m.group(2)).replace(",", "")))


def facts(line: Line) -> list[tuple[str, str]]:
    """(label, value) pairs that must agree everywhere, e.g. ("annual fee, grade 1 to 5", "Rs 25,000")."""
    found = []
    group = class_group(line.text)
    for segment in re.split(r"[|;]", line.text):
        seg = segment.lower()
        fee_type = next((t for t in FEE_TYPES if re.search(rf"\b{t}\b", seg)), None)
        for m in AMOUNT_RE.finditer(segment):
            if fee_type:
                label = f"{fee_type} fee" + (f", {group}" if group else "")
                found.append((label, f"Rs {_amount(m):,}"))
    low = line.text.lower()
    for event in EVENTS:
        at = re.search(rf"\b{event}s?\b", low)
        if at:
            dates = list(DATE_RANGE_RE.finditer(line.text[at.start():])) or list(DATE_RANGE_RE.finditer(line.text))
            if len(dates) >= 2 and dates[0].group(6) and dates[1].group(6):  # "From: 18 Oct 2027 | To: 20 Oct 2027"
                found.append((event, join_dates(dates[0], dates[1])))
            elif dates:
                open_ended = dates[0].group(6) and re.search(r"\bfrom:?\s+\d", low)  # "from 1 May 2028", no end
                found.append((event, ("from " if open_ended else "") + normalise_dates(dates[0])))
    role = next((r for r in ROLES if re.search(rf"\b{r}\b", low)), None)
    if role:
        for p in PHONE_RE.findall(line.text):
            found.append((f"{role} phone", re.sub(r"\D", "", p)[-10:]))
        for e in EMAIL_RE.findall(line.text):
            found.append((f"{role} email", e.lower()))
    return found


def normalise_dates(m: re.Match) -> str:
    """ "8-11 Nov 2027" -> "8 to 11 November 2027"; "25 Dec" -> "25 December" (DATE_RANGE_RE groups)."""
    if m.group(6):  # a single date
        return " ".join(filter(None, [str(int(m.group(6))), _month(m.group(7)), m.group(8)]))
    end_month = _month(m.group(4))
    start_month = _month(m.group(2)) or end_month
    start = str(int(m.group(1))) if start_month == end_month else f"{int(m.group(1))} {start_month}"
    return f"{start} to {int(m.group(3))} {end_month}" + (f" {m.group(5)}" if m.group(5) else "")


def join_dates(first: re.Match, last: re.Match) -> str:
    """Two single dates (a From and a To column) written like a range: "18 to 20 October 2027"."""
    d1, m1, y1 = int(first.group(6)), _month(first.group(7)), first.group(8)
    d2, m2, y2 = int(last.group(6)), _month(last.group(7)), last.group(8)
    if y1 and y2 and y1 != y2:
        return f"{d1} {m1} {y1} to {d2} {m2} {y2}"
    if (d1, m1) == (d2, m2):  # a one-day holiday
        return f"{d1} {m1}" + (f" {y1 or y2}" if (y1 or y2) else "")
    start = str(d1) if m1 == m2 else f"{d1} {m1}"
    return f"{start} to {d2} {m2}" + (f" {y2 or y1}" if (y2 or y1) else "")


def _month(name: str | None) -> str:
    if not name:
        return ""
    full = next(k for k in MONTHS if k.startswith(name.lower()[:3]))
    return full.capitalize()


# ---------- Building the drafts ----------

def ingest(incoming: Path, campus: str = "pilot-campus") -> Result:
    files = sorted(p for p in incoming.rglob("*") if p.is_file() and not p.name.startswith((".", "~$")))
    all_lines: list[Line] = []
    manual, read = [], []
    for path in files:
        name = path.relative_to(incoming).as_posix()
        try:
            raw, how = read_document(path)
        except ValueError as e:
            manual.append((name, str(e)))
            continue
        except Exception as e:  # a damaged file must not stop the others
            manual.append((name, f"could not be read ({type(e).__name__}); open it and type the content in"))
            continue
        lines = clean_lines(raw, name)
        hint = next((topic_for(Line(t.text, "", "")) for t in lines if is_title(t) and topic_for(t)), None)
        hint = hint or topic_for(Line(path.stem.replace("-", " ").replace("_", " "), "", ""))
        kept = []
        for line in lines:
            if is_title(line):
                continue
            line.topic_hint = hint
            flag_unclear(line)
            kept.append(line)
        all_lines += kept
        read.append((name, how, len(kept)))

    conflicts = find_conflicts(all_lines)
    by_file: dict[str, dict[str | None, list[Line]]] = defaultdict(lambda: defaultdict(list))
    unsorted = []
    for line in all_lines:
        file = topic_for(line)
        if file is None:
            unsorted.append(line)
            continue
        by_file[file][section_for(file, line)].append(line)

    drafts, missing = {}, []
    for file in REQUIRED:
        drafts[file] = render(file, by_file.get(file, {}), all_lines, missing)
    return Result(drafts, all_lines, unsorted, manual, read, conflicts, missing)


def find_conflicts(lines: list[Line]) -> list[dict]:
    seen: dict[str, dict[str, list[Line]]] = defaultdict(lambda: defaultdict(list))
    for line in lines:
        for label, value in facts(line):
            seen[label][value].append(line)
    conflicts = []
    for label, values in seen.items():
        if len(values) > 1:
            where = {v: sorted({l.source for l in ls}) for v, ls in values.items()}
            conflicts.append({"label": label, "values": where})
            for value, ls in values.items():
                others = ", ".join(f"{v} ({'; '.join(w)})" for v, w in where.items() if v != value)
                for l in ls:
                    reason = f"conflict: {label} is {value} here but {others}"
                    if reason not in l.reasons:
                        l.reasons.append(reason)
    return conflicts


def section_headings(file: str) -> list[str]:
    """The "##" headings of the current kb file (text in brackets left out: it can hold facts)."""
    path = ROOT / "kb" / "pilot-campus" / file
    if not path.exists():
        return []
    return [re.sub(r"\s*\(.*\)\s*$", "", l[3:]).strip() for l in path.read_text(encoding="utf-8").splitlines()
            if l.startswith("## ")]


def render_line(line: Line) -> str:
    text = line.text
    if line.reasons:
        text += f" {MARK}: " + "; ".join(dict.fromkeys(line.reasons))
    return f"- {text} <!-- source: {line.source} -->"


def render(file: str, sections: dict, all_lines: list[Line], missing: list[str]) -> str:
    title = REQUIRED[file][0]
    out = [title, f"> DRAFT made by scripts/ingest_docs.py on {date.today():%d %b %Y}. Check every line against the "
                  f"source document, fix or delete every {MARK}, then run scripts/approve_kb.py.", ""]
    headings = section_headings(file)
    content = [l for ls in sections.values() for l in ls]
    if headings:
        for h in headings:
            out.append(f"## {h}")
            items = sections.get(h, [])
            if items:
                out += [render_line(l) for l in items]
            else:
                out.append(f"{NOT_PROVIDED} {MARK}: no document covers this; ask the school for it.")
                missing.append(f"{file}, section '{h}'")
            out.append("")
    elif content:
        out += [render_line(l) for l in content]
    else:
        out.append(f"{NOT_PROVIDED} {MARK}: no document covers this; ask the school for {ASK_FOR[file]}.")
        missing.append(file)

    for needed in REQUIRED_LINES.get(file, []):
        if needed == "Holidays:":
            out.append(holidays_line(all_lines))
        elif not any(needed.lower() in l.text.lower() for l in content):
            out.append(f"- {needed}: {NOT_PROVIDED} {MARK}: the chatbot needs this line; ask the school.")
            missing.append(f"{file}, line '{needed}'")
    return "\n".join(out).rstrip() + "\n"


def holidays_line(lines: list[Line]) -> str:
    """calendar.md needs one "Holidays:" line (the code reads it). Built only from dates found in the documents."""
    holidays: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        for label, value in facts(line):
            if label in EVENTS and "exam" not in label and label not in ("academic year", "reopening"):
                holidays[label].add(value)
    if not holidays:
        return f"- Holidays: {NOT_PROVIDED} {MARK}: no holiday dates found; ask the school for the holiday list."
    parts = []
    for name, values in holidays.items():
        shown = " / ".join(sorted(values))
        parts.append(f"{name.title()} {shown}")
    return (f"- Holidays: {'. '.join(parts)}. {MARK}: built from the dated lines in the documents; check every name "
            f"and date, add the year to each date, and keep this one-line format (see kb/pilot-campus/calendar.md).")


# ---------- The review report ----------

def write_report(result: Result, path: Path, incoming: Path, drafts_dir: Path) -> None:
    flagged = [l for l in result.lines if l.reasons and not any(r.startswith("conflict") for r in l.reasons)]
    out = [f"# Content review ({date.today():%d %b %Y})", "",
           f"Made by `scripts/ingest_docs.py` from the documents in `{incoming.name}/`. Drafts are in "
           f"`{drafts_dir.as_posix()}/`. Nothing here is in the chatbot yet.", "",
           "Send the **Questions for the school** to the school. When the answers come back, fix the drafts, remove every "
           f"\"{MARK}\", then run `python scripts/approve_kb.py`.", "",
           "## Documents read", "", "| File | Read as | Lines |", "|---|---|---|"]
    out += [f"| {f} | {how} | {n} |" for f, how, n in result.read]
    if result.manual:
        out += ["", "## Needs manual typing", ""]
        out += [f"- **{f}**: {why}" for f, why in result.manual]

    # Misread text and possible personal data are checked by the reviewer against the originals;
    # everything else is a question only the school can answer.
    for_reviewer = [l for l in flagged if all(r.startswith(REVIEWER_REASONS) for r in l.reasons)]
    for_school = [l for l in flagged if l not in for_reviewer]
    missing_by_file: dict[str, list[str]] = defaultdict(list)
    for item in result.missing:
        file, _, part = item.partition(", ")
        missing_by_file[file].append(part)

    out += ["", "## Questions for the school", ""]
    n = 0
    for c in result.conflicts:
        n += 1
        values = "; ".join(f"{v} in {', '.join(w)}" for v, w in c["values"].items())
        out.append(f"{n}. **Conflicting:** {c['label']}: {values}. Which is correct?")
    for file, parts in missing_by_file.items():
        n += 1
        what = f" ({', '.join(p for p in parts if p)})" if any(parts) else ""
        out.append(f"{n}. **Missing:** {file}{what}. Please send {ASK_FOR[file]}.")
    for line in for_school:
        n += 1
        reasons = "; ".join(r for r in line.reasons if not r.startswith(REVIEWER_REASONS))
        out.append(f"{n}. **Please confirm:** \"{line.text}\" ({line.source}): {reasons}.")
    if n == 0:
        out.append("None.")
    if for_reviewer:
        out += ["", "## For the reviewer: check against the original documents", ""]
        out += [f"- \"{l.text}\" ({l.source}): {'; '.join(l.reasons)}." for l in for_reviewer]
    if result.unsorted:
        out += ["", "## Lines not sorted into any file", "",
                "These lines did not match any topic. Add them to the right draft by hand, or ignore them.", ""]
        out += [f"- \"{l.text}\" ({l.source})" for l in result.unsorted]
    out += ["", "## Not done by this script", "",
            "- `kb/pilot-campus/routing.json` (who gets which concern, role emails) and `config/working_days.json` "
            "(holidays) must be updated by hand to match the approved escalation.md, contacts.md and calendar.md. "
            "`python scripts/check_kb.py --live` checks they agree.",
            "- `kb/school.json` (school name, campuses) is updated by hand."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incoming", default=str(ROOT / "incoming"))
    parser.add_argument("--drafts", default=str(ROOT / "drafts"))
    parser.add_argument("--campus", default="pilot-campus")
    parser.add_argument("--report", default=str(ROOT / "docs" / "content-review.md"))
    args = parser.parse_args()

    incoming = Path(args.incoming)
    if not incoming.is_dir() or not any(incoming.iterdir()):
        print(f"Put the school's documents in {incoming} first.")
        return 1
    result = ingest(incoming, args.campus)
    out_dir = Path(args.drafts) / args.campus
    out_dir.mkdir(parents=True, exist_ok=True)
    for file, text in result.drafts.items():
        (out_dir / file).write_text(text, encoding="utf-8", newline="\n")
    write_report(result, Path(args.report), incoming, out_dir.relative_to(ROOT) if out_dir.is_relative_to(ROOT) else out_dir)

    marks = sum(text.count(MARK) for text in result.drafts.values())
    print(f"Read {len(result.read)} document(s); {len(result.manual)} need manual typing.")
    print(f"Drafts: {out_dir} ({len(result.drafts)} files, {marks} '{MARK}' marks)")
    print(f"Conflicts: {len(result.conflicts)}. Missing: {len(result.missing)}. Unsorted lines: {len(result.unsorted)}.")
    print(f"Questions for the school: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

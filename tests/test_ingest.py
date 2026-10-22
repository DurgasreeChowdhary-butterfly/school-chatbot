"""scripts/ingest_docs.py and scripts/approve_kb.py with three fake messy documents (tests/messy_docs.py)."""
import re
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("pypdf")
pytest.importorskip("docx")
pytest.importorskip("fpdf")

from scripts import approve_kb, ingest_docs  # noqa: E402
from scripts.check_kb import REQUIRED  # noqa: E402
from tests.messy_docs import make_messy_docs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ingested(tmp_path):
    incoming = tmp_path / "incoming"
    make_messy_docs(incoming)
    result = ingest_docs.ingest(incoming)
    drafts = tmp_path / "drafts" / "pilot-campus"
    drafts.mkdir(parents=True)
    for name, text in result.drafts.items():
        (drafts / name).write_text(text, encoding="utf-8")
    report = tmp_path / "content-review.md"
    ingest_docs.write_report(result, report, incoming, drafts)
    return result, drafts, report, incoming


def test_every_file_is_drafted_with_its_headings(ingested):
    result, drafts, _, _ = ingested
    assert [r[1] for r in result.read] == ["Word", "PDF text", "text"]
    assert set(result.drafts) == set(REQUIRED)
    for name, headings in REQUIRED.items():
        text = (drafts / name).read_text(encoding="utf-8")
        for h in headings:
            assert any(line.startswith(h) for line in text.splitlines()), (name, h)


def test_conflicting_fee_is_marked_in_both_places_and_asked(ingested):
    result, drafts, report, _ = ingested
    [conflict] = result.conflicts
    assert conflict["label"] == "annual fee, grade 1 to 5"
    assert set(conflict["values"]) == {"Rs 26,000", "Rs 27,000"}
    fees = (drafts / "fees.md").read_text(encoding="utf-8")
    assert fees.count("NEEDS REVIEW: conflict: annual fee, grade 1 to 5") == 2
    assert "Conflicting:** annual fee, grade 1 to 5: Rs 26,000 in fee-circular-2027.pdf" in report.read_text(encoding="utf-8")


def test_unclear_lines_are_marked(ingested):
    _, drafts, report, _ = ingested
    text = "\n".join(p.read_text(encoding="utf-8") for p in drafts.glob("*.md"))
    assert "(amount tentative). NEEDS REVIEW: not final ('tentative')" in text
    assert "Hostel: n0t available NEEDS REVIEW: text may be misread" in text
    assert "relative date, not an exact date" in text                     # "PTM next Saturday"
    assert "start date only, no end date" in text                         # summer vacation
    assert "9876501234 NEEDS REVIEW: a mobile number without a school role" in text
    assert "For the reviewer: check against the original documents" in report.read_text(encoding="utf-8")


def test_missing_topics_say_not_provided(ingested):
    result, drafts, _, _ = ingested
    hiring = (drafts / "hiring.md").read_text(encoding="utf-8")
    assert "Not provided. NEEDS REVIEW: no document covers this" in hiring
    assert "privacy_notice.md" in result.missing and "hiring.md" in result.missing
    contacts = (drafts / "contacts.md").read_text(encoding="utf-8")
    assert "- Admission counsellor: Ms. Sample Counsellor" in contacts      # required line found and placed here
    assert "Admission counsellor: Not provided" not in contacts


def test_holidays_line_is_built_only_from_document_dates(ingested):
    _, drafts, _, _ = ingested
    [line] = [l for l in (drafts / "calendar.md").read_text(encoding="utf-8").splitlines() if l.startswith("- Holidays:")]
    assert "Dussehra 18 to 20 October 2027" in line and "Christmas 25 December 2027" in line
    assert "Summer Vacation from 1 May 2028" in line and "NEEDS REVIEW" in line


def test_no_number_appears_that_is_not_in_the_documents(ingested):
    """Never invent facts: every number in the drafts' content comes from the source documents."""
    result, drafts, _, incoming = ingested
    source_text = " ".join(l.text for l in result.lines)
    source_numbers = set(re.findall(r"\d+", source_text.replace(",", "")))
    for path in drafts.glob("*.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(">"):
                continue  # the draft note (today's date)
            content = re.sub(r"<!--.*?-->", "", line).replace(",", "")
            for number in re.findall(r"\d+", content):
                assert number in source_numbers, (path.name, number, line)


def test_unreadable_files_are_listed_for_manual_typing(tmp_path, monkeypatch):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "old-circular.doc").write_bytes(b"\xd0\xcf\x11\xe0 old word file")
    (incoming / "notice.jpg").write_bytes(b"not really a photo")
    (incoming / "broken.pdf").write_bytes(b"%PDF-1.4 broken")
    monkeypatch.setattr(ingest_docs, "ocr_image", lambda path: None)  # a computer without Windows OCR
    result = ingest_docs.ingest(incoming)
    why = dict(result.manual)
    assert ".doc files cannot be read" in why["old-circular.doc"]
    assert "Windows OCR is not available" in why["notice.jpg"]
    assert "broken.pdf" in why
    assert result.read == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows OCR")
def test_photo_is_read_with_windows_ocr(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    img = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(img).text((20, 30), "Front office phone +91 00000 00001", fill="black",
                             font=ImageFont.truetype("arial.ttf", 34))
    img.save(incoming / "notice.png")
    result = ingest_docs.ingest(incoming)
    if result.manual:
        pytest.skip(f"Windows OCR not available here: {result.manual}")
    assert result.read[0][1] == "photo (OCR)"
    assert "Front office phone: Not provided" not in result.drafts["contacts.md"]
    assert "+91 00000 00001" in result.drafts["contacts.md"]


# ---------- approve_kb ----------

def review(drafts: Path) -> None:
    """What a person does: fix each marked line (here: just delete the marks)."""
    for path in drafts.glob("*.md"):
        text = re.sub(r" ?NEEDS REVIEW:[^<\n]*", "", path.read_text(encoding="utf-8"))
        path.write_text(text, encoding="utf-8")


def test_approve_refuses_while_marks_remain(ingested, tmp_path):
    _, drafts, _, _ = ingested
    kb = tmp_path / "kb" / "pilot-campus"
    shutil.copytree(ROOT / "kb" / "pilot-campus", kb)
    before = (kb / "fees.md").read_text(encoding="utf-8")
    copied, problems = approve_kb.approve(drafts, kb)
    assert copied == [] and "fees.md" in problems and "line" in problems["fees.md"][0]
    assert (kb / "fees.md").read_text(encoding="utf-8") == before


def test_approve_copies_reviewed_drafts_without_notes_and_backs_up(ingested, tmp_path):
    _, drafts, _, _ = ingested
    kb = tmp_path / "kb" / "pilot-campus"
    shutil.copytree(ROOT / "kb" / "pilot-campus", kb)
    review(drafts)
    copied, problems = approve_kb.approve(drafts, kb)
    assert problems == {} and set(copied) == set(REQUIRED)
    fees = (kb / "fees.md").read_text(encoding="utf-8")
    assert fees.startswith("# Fee structure\n") and "Rs 26,000" in fees
    assert "<!--" not in fees and "DRAFT" not in fees and "NEEDS REVIEW" not in fees
    [backup] = list((drafts.parent / "_replaced").iterdir())
    assert "DUMMY DATA" in (backup / "fees.md").read_text(encoding="utf-8")   # the old file was kept


def test_partial_approve_copies_only_ready_files(ingested, tmp_path):
    _, drafts, _, _ = ingested
    kb = tmp_path / "kb" / "pilot-campus"
    kb.mkdir(parents=True)
    copied, problems = approve_kb.approve(drafts, kb, partial=True)
    assert "discounts_policy.md" in copied and "fees.md" not in copied
    assert sorted(p.name for p in kb.iterdir()) == sorted(copied)


def test_draft_missing_a_heading_is_not_ready(ingested, tmp_path):
    _, drafts, _, _ = ingested
    review(drafts)
    admissions = drafts / "admissions.md"
    admissions.write_text(admissions.read_text(encoding="utf-8").replace("## Age criteria", "## Ages"), encoding="utf-8")
    copied, problems = approve_kb.approve(drafts, tmp_path / "kb")
    assert copied == [] and problems == {"admissions.md": ["heading '## Age criteria' missing"]}

"""The ingest rehearsal with harder documents, and the improvements it led to."""
import sys

import pytest

pytest.importorskip("pypdf")
pytest.importorskip("docx")
pytest.importorskip("openpyxl")
pytest.importorskip("PIL")

from scripts import ingest_docs, ingest_rehearsal  # noqa: E402


def test_rehearsal_gets_the_facts(tmp_path):
    rows = ingest_rehearsal.rehearse(tmp_path / "docs")
    verdicts = {r["doc"]: [v for _, v in r["verdicts"]] for r in rows}
    ocr = sys.platform == "win32" and rows[0]["how"] == "photo (OCR)"
    for doc in ("fee-table-columns.pdf", "calendar-merged.docx", "fees-workbook.xlsx"):
        assert set(verdicts[doc]) == {"right"}, (doc, verdicts[doc])
    assert set(verdicts["notice-mixed-language.docx"]) <= {"right", "flagged"}    # flagged = translate to English
    if ocr:
        assert set(verdicts["notice-phone-photo.jpg"]) == {"right"}
        assert set(verdicts["scanned-admissions.pdf"]) == {"right"}


def test_pdf_table_columns_keep_their_headings():
    lines = ingest_docs.label_columns(["FEE STRUCTURE", "Class Admission fee Annual fee Term fee",
                                       "Grade 1 to 5 Rs 12,000 Rs 26,000 Rs 18,500", "Transport is extra."])
    assert lines[2] == "Grade 1 to 5 | Admission fee: Rs 12,000 | Annual fee: Rs 26,000 | Term fee: Rs 18,500"
    assert lines[3] == "Transport is extra."


def test_table_title_rows_are_not_headings():
    rows = [["Fees 2027-28", "Fees 2027-28", "Fees 2027-28"], ["Class", "Annual fee", "Term fee"],
            ["Grade 1 to 5", "Rs 26,000", "Rs 18,500"]]
    [(text, where)] = ingest_docs._table_lines(rows, "sheet 'Fees'")
    assert text == "Grade 1 to 5 | Annual fee: Rs 26,000 | Term fee: Rs 18,500"
    assert where == "sheet 'Fees' (Fees 2027-28), row 2"


def test_ocr_slips_and_indian_languages():
    assert ingest_docs.fix_ocr("P TM on 25 September") == "PTM on 25 September"
    line = ingest_docs.Line("Diwali (दीपावली) holidays: 27 to 30 October 2027", "x", "x")
    ingest_docs.flag_unclear(line)
    assert line.reasons == ["contains Hindi or Telugu words: write the line in English (the chatbot answers in English)"]

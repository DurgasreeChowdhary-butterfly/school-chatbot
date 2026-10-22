"""Six harder fake school documents (DUMMY content) for the ingest rehearsal (scripts/ingest_rehearsal.py), and the
facts each one contains, so what the ingest script gets right can be measured.

- notice-phone-photo.jpg: a notice photographed with a phone: rotated, shadow on one side, noise, blur, low JPEG quality
- scanned-admissions.pdf: a scanned circular: the PDF holds only a picture of the page, no text
- fee-table-columns.pdf: a fee table in columns (headings in the first row only)
- calendar-merged.docx: Word tables with a merged title row and a cell merged down two rows
- fees-workbook.xlsx: Excel with three sheets, merged title rows and a merged cell down two rows
- notice-mixed-language.docx: English with Hindi and Telugu words

Make them by hand:  python -m tests.hard_docs some-folder"""
import random
import sys
from pathlib import Path

FONT = "arial.ttf"

PHOTO_LINES = [
    "NOTICE TO PARENTS",
    "Office hours: Monday to Friday 8:30 to 16:30",
    "Front office phone: +91 00000 00001",
    "PTM for all classes on 25 September 2027, 9:30 to 12:30",
    "Bus stop requests: contact the transport coordinator",
]
SCAN_LINES = [
    "ADMISSIONS 2027-28 CIRCULAR",
    "Age criteria (as on 31 May 2027): Nursery 3 years, Grade 1: 6 years.",
    "Admission test for Grade 2 and above on 13 March 2028.",
    "Documents: birth certificate, Aadhaar card, transfer certificate.",
    "Hostel facilities are not available.",
]
FEE_ROWS = [("Class", "Admission fee", "Annual fee", "Term fee"),
            ("Nursery to UKG", "Rs 10,000", "Rs 21,000", "Rs 15,500"),
            ("Grade 1 to 5", "Rs 12,000", "Rs 26,000", "Rs 18,500"),
            ("Grade 6 to 8", "Rs 15,000", "Rs 31,000", "Rs 22,500"),
            ("Grade 9 to 10", "Rs 18,000", "Rs 36,000", "Rs 26,500")]
HOLIDAYS = [("Dussehra", "18 October 2027", "20 October 2027"), ("Diwali", "27 October 2027", "30 October 2027"),
            ("Christmas", "25 December 2027", "25 December 2027"), ("Sankranti", "13 January 2028", "16 January 2028")]
MIXED = [
    "Diwali (दीपावली) holidays: 27 to 30 October 2027",
    "PTM (తల్లిదండ్రుల సమావేశం) on 25 September 2027, 9:30 to 12:30",
    "Fees can be paid at the accounts office (लेखा कार्यालय) from 9:00 to 15:00 on working days.",
    "Bus (బస్సు) routes: North, South, East and Central.",
]

# What each document says, for measuring. kind: fee (file, label, value) / holiday (name, dates) / text (file, words)
FACTS = {
    "notice-phone-photo.jpg": [
        ("text", "contacts.md", "Office hours: Monday to Friday 8:30 to 16:30"),
        ("text", "contacts.md", "Front office phone: +91 00000 00001"),
        ("text", "ptm.md", "25 September 2027"),
        ("text", "transport.md", "transport coordinator"),
    ],
    "scanned-admissions.pdf": [
        ("text", "admissions.md", "Grade 1: 6 years"),
        ("text", "admissions.md", "13 March 2028"),
        ("text", "documents.md", "birth certificate"),
        ("text", "admissions.md", "Hostel facilities are not available"),
    ],
    "fee-table-columns.pdf": [("fee", "fees.md", f"{kind.lower()}, {row[0].lower()}", value)
                              for row in FEE_ROWS[1:] for kind, value in zip(("Admission fee", "Annual fee", "Term fee"),
                                                                             row[1:])],
    "calendar-merged.docx": [("holiday", name, f"{a.split()[0]} to {b}" if a != b else a) for name, a, b in HOLIDAYS]
                            + [("text", "calendar.md", "13 to 20 September 2027")],
    "fees-workbook.xlsx": [("fee", "fees.md", f"annual fee, {row[0].lower()}", row[2]) for row in FEE_ROWS[1:]]
                          + [("text", "transport.md", "North"), ("text", "transport.md", "Rs 9,000"),
                             ("text", "contacts.md", "+91 00000 00002")],
    "notice-mixed-language.docx": [("holiday", "Diwali", "27 to 30 October 2027"),
                                   ("text", "ptm.md", "25 September 2027"),
                                   ("text", "fees.md", "accounts office"),
                                   ("text", "transport.md", "North, South, East and Central")],
}


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def _page_image(lines, size=(1240, 1754), font_size=34, top=140, gap=70, paper=(255, 255, 255)):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, paper)
    draw = ImageDraw.Draw(img)
    for n, line in enumerate(lines):
        draw.text((90, top + n * gap), line, fill=(30, 30, 30), font=_font(font_size + (6 if n == 0 else 0)))
    return img


def make_photo(path: Path) -> None:
    from PIL import Image, ImageFilter
    random.seed(7)
    img = _page_image(PHOTO_LINES, size=(1500, 620), font_size=38, top=50, gap=105, paper=(236, 230, 216))
    shadow = Image.linear_gradient("L").rotate(90).resize(img.size)          # dark on the left, light on the right
    img = Image.composite(img, Image.new("RGB", img.size, (95, 90, 80)), shadow.point(lambda v: 110 + v * 145 // 255))
    noise = Image.effect_noise(img.size, 28).convert("RGB")
    img = Image.blend(img, noise, 0.12)
    img = img.rotate(3.5, expand=True, fillcolor=(70, 65, 60), resample=Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(0.9))
    img.save(path, "JPEG", quality=55)


def make_scanned_pdf(path: Path, tmp: Path) -> None:
    from fpdf import FPDF
    from PIL import Image
    page = _page_image(SCAN_LINES)
    page = Image.blend(page, Image.effect_noise(page.size, 20).convert("RGB"), 0.06).rotate(0.7, fillcolor="white")
    picture = tmp / "scan-page.png"
    page.save(picture)
    pdf = FPDF()
    pdf.add_page()
    pdf.image(str(picture), x=0, y=0, w=210, h=297)  # the whole page is a picture: no text layer
    pdf.output(str(path))
    picture.unlink()


def make_fee_table_pdf(path: Path) -> None:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "FEE STRUCTURE 2027-28", new_x="LMARGIN", new_y="NEXT")
    for n, row in enumerate(FEE_ROWS):
        pdf.set_font("Helvetica", "B" if n == 0 else "", 11)
        for width, cell in zip((55, 42, 42, 42), row):
            pdf.cell(width, 9, cell, border=1)
        pdf.ln()
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 8, "Transport, uniform and books are charged separately.", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def make_merged_docx(path: Path) -> None:
    from docx import Document
    doc = Document()
    doc.add_heading("ACADEMIC CALENDAR 2027-28", level=1)
    t = doc.add_table(rows=2 + len(HOLIDAYS), cols=3)
    title = t.rows[0].cells[0].merge(t.rows[0].cells[2])
    title.text = "HOLIDAYS 2027-28"
    for cell, text in zip(t.rows[1].cells, ("Holiday", "From", "To")):
        cell.text = text
    for row, values in zip(t.rows[2:], HOLIDAYS):
        for cell, text in zip(row.cells, values):
            cell.text = text
    exams = doc.add_table(rows=3, cols=3)
    for cell, text in zip(exams.rows[0].cells, ("Term", "Exam", "Dates")):
        cell.text = text
    term = exams.rows[1].cells[0].merge(exams.rows[2].cells[0])  # "Term 1" spans two rows
    term.text = "Term 1"
    exams.rows[1].cells[1].text, exams.rows[1].cells[2].text = "Unit test", "4 to 6 August 2027"
    exams.rows[2].cells[1].text, exams.rows[2].cells[2].text = "Term 1 exams", "13 to 20 September 2027"
    doc.save(path)


def make_workbook(path: Path) -> None:
    import openpyxl
    wb = openpyxl.Workbook()
    fees = wb.active
    fees.title = "Fees"
    fees.append(["Fee structure 2027-28"])
    fees.merge_cells("A1:D1")
    for row in FEE_ROWS:
        fees.append(list(row))
    transport = wb.create_sheet("Transport")
    transport.append(["Bus fees 2027-28"])
    transport.merge_cells("A1:C1")
    transport.append(["Route", "Distance", "Fee per year"])
    transport.append(["North", "0 to 5 km", "Rs 9,000"])
    transport.append([None, "5 to 12 km", "Rs 12,000"])
    transport.merge_cells("A3:A4")                                  # "North" spans two rows
    transport.append(["South", "0 to 5 km", "Rs 9,000"])
    contacts = wb.create_sheet("Contacts")
    contacts.append(["Role", "Phone", "Email"])
    contacts.append(["Front office", "+91 00000 00001", "frontoffice.campusa@example.com"])
    contacts.append(["Admission counsellor", "+91 00000 00002", "admissions.campusa@example.com"])
    wb.save(path)


def make_mixed_docx(path: Path) -> None:
    from docx import Document
    doc = Document()
    doc.add_heading("NOTICE / सूचना / ప్రకటన", level=1)
    for line in MIXED:
        doc.add_paragraph(line)
    doc.save(path)


def make_hard_docs(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = {name: folder / name for name in FACTS}
    make_photo(paths["notice-phone-photo.jpg"])
    make_scanned_pdf(paths["scanned-admissions.pdf"], folder)
    make_fee_table_pdf(paths["fee-table-columns.pdf"])
    make_merged_docx(paths["calendar-merged.docx"])
    make_workbook(paths["fees-workbook.xlsx"])
    make_mixed_docx(paths["notice-mixed-language.docx"])
    return list(paths.values())


if __name__ == "__main__":
    for p in make_hard_docs(Path(sys.argv[1] if len(sys.argv) > 1 else "rehearsal-docs")):
        print("made", p)

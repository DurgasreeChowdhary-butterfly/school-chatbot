"""Rehearse the ingest with six harder fake documents and measure what it gets right.

Usage:  python scripts/ingest_rehearsal.py              # writes docs/ingest-rehearsal.md and a sample docs/content-review.md

For each document (tests/hard_docs.py) it runs scripts/ingest_docs.py on that document alone and checks every fact the
document contains: "right" (in the right draft file, unmarked), "flagged" (in the right file but marked NEEDS REVIEW,
so a person checks it), "wrong file" (found, but sorted into another file) or "missing" (not found).
Then all six are ingested together to make the sample review report with the manual-typing list.
Photos the school sent (in incoming/) are also OCR-read, but only line counts are reported: their content is never
written to the repository, and they are never committed (incoming/ is in .gitignore)."""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import ingest_docs  # noqa: E402
from tests.hard_docs import FACTS, make_hard_docs  # noqa: E402

MARK = ingest_docs.MARK


def _lines(text: str) -> list[str]:
    return [re.sub(r"\s*<!--.*?-->", "", l) for l in text.splitlines() if l.startswith("- ") or l.startswith("Not provided")]


def _contains(line: str, words: str) -> bool:
    pattern = r"\s*".join(re.escape(w) for w in words.split())
    return bool(re.search(pattern, line, re.I))


def judge(fact: tuple, drafts: dict[str, str]) -> str:
    kind = fact[0]
    if kind == "holiday":
        _, name, dates = fact
        line = next((l for l in _lines(drafts["calendar.md"]) if l.startswith("- Holidays:")), "")
        return "right" if _contains(line, f"{name} {dates}") else "missing"

    def found_in(file: str) -> list[str]:
        if kind == "fee":
            _, _, label, value = fact
            return [l for l in _lines(drafts[file])
                    if (label, value) in ingest_docs.facts(ingest_docs.Line(l.split(MARK)[0], "", ""))]
        return [l for l in _lines(drafts[file]) if _contains(l.split(MARK)[0], fact[2])]

    hits = found_in(fact[1])
    if hits:
        return "flagged" if all(MARK in h for h in hits) else "right"
    if any(found_in(f) for f in drafts if f != fact[1]):
        return "wrong file"
    return "missing"


def rehearse(folder: Path) -> list[dict]:
    rows = []
    for path in make_hard_docs(folder):
        single = folder / f"only-{path.stem}"
        single.mkdir()
        path.replace(single / path.name)
        result = ingest_docs.ingest(single)
        how = result.read[0][1] if result.read else "manual typing: " + result.manual[0][1]
        verdicts = [(fact, judge(fact, result.drafts)) for fact in FACTS[path.name]]
        rows.append({"doc": path.name, "how": how, "verdicts": verdicts,
                     "marks": sum(t.count(MARK) for t in result.drafts.values())})
        (single / path.name).replace(path)
    return rows


def real_photos() -> list[tuple[str, str]]:
    incoming = ROOT / "incoming"
    out = []
    for p in sorted(incoming.glob("*")) if incoming.is_dir() else []:
        if p.suffix.lower() in ingest_docs.IMAGE_TYPES:
            text = ingest_docs.ocr_image(p)
            out.append((p.name, "OCR not available" if text is None else f"{len(text.splitlines())} lines read"))
    return out


def describe(fact: tuple) -> str:
    if fact[0] == "fee":
        return f"{fact[2]} = {fact[3]}"
    if fact[0] == "holiday":
        return f"Holidays line: {fact[1]} {fact[2]}"
    return f"'{fact[2]}' in {fact[1]}"


def write_report(rows: list[dict], photos: list, path: Path) -> dict:
    totals = {"right": 0, "flagged": 0, "wrong file": 0, "missing": 0}
    out = ["# Ingest rehearsal (harder fake documents)", "",
           "Made by `scripts/ingest_rehearsal.py`. Each fake document (`tests/hard_docs.py`) was ingested alone and every "
           "fact it contains was checked in the drafts. **Right** = in the right file, unmarked. **Flagged** = in the "
           "right file but marked NEEDS REVIEW (a person checks it). **Wrong file** = sorted into another file. "
           "**Missing** = not found.", "",
           "| Document | Read as | Facts | Right | Flagged | Wrong file | Missing |", "|---|---|---|---|---|---|---|"]
    details = []
    for r in rows:
        count = {k: sum(v == k for _, v in r["verdicts"]) for k in totals}
        for k in totals:
            totals[k] += count[k]
        out.append(f"| {r['doc']} | {r['how']} | {len(r['verdicts'])} | {count['right']} | {count['flagged']} | "
                   f"{count['wrong file']} | {count['missing']} |")
        details += [f"- {r['doc']}: {describe(f)}: **{v}**" for f, v in r["verdicts"] if v != "right"]
    n = sum(totals.values())
    out += ["", f"**Total: {n} facts: {totals['right']} right, {totals['flagged']} flagged, {totals['wrong file']} in the "
                f"wrong file, {totals['missing']} missing.**", "", "## Facts not simply right", ""]
    out += details or ["None."]
    out += ["", "## Before the improvements", "",
            "First measured on 22 Oct 2026 with the same documents: 11 right, 2 flagged, 3 in the wrong file, 20 missing "
            "(36 facts). Changes since: scanned PDF pages are read with OCR; column headings from a PDF table are kept "
            "with each row; title rows of tables are used as titles, not headings; Excel merged cells are filled in; "
            "Word cells merged across columns are kept once; the sheet name or table title decides the file for its "
            "rows; OCR's split \"P TM\" is joined; Hindi and Telugu words get their own review reason.",
            "", "These documents were written by the same person who improved the script, so real documents will score "
            "lower. Run this again with the school's documents in mind, and always read the drafts."]
    out += ["", "## Photos from the school (incoming/)", ""]
    out += [f"- {name}: {what} (content not shown here)" for name, what in photos] or [
        "None found. When the school's photos arrive, run this again to see how many lines OCR reads from each."]
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    return totals


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "docs"
        rows = rehearse(folder)
        totals = write_report(rows, real_photos(), ROOT / "docs" / "ingest-rehearsal.md")
        together = ingest_docs.ingest(folder)
        ingest_docs.write_report(together, ROOT / "docs" / "content-review.md", folder, Path("drafts/pilot-campus"))
    review = ROOT / "docs" / "content-review.md"
    text = review.read_text(encoding="utf-8")
    review.write_text(text.replace("\nMade by", "\n> **Sample.** Made from the six harder FAKE documents in "
                                   "`tests/hard_docs.py` by `scripts/ingest_rehearsal.py`. Running `scripts/ingest_docs.py` on "
                                   "the school's documents replaces it.\n\nMade by", 1), encoding="utf-8", newline="\n")
    for r in rows:
        print(f"{r['doc']:<30} {r['how']:<14} " + ", ".join(f"{k}: {sum(v == k for _, v in r['verdicts'])}"
                                                          for k in totals))
    print("Total:", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())

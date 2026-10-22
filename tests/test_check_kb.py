"""scripts/check_kb.py: the checklist for swapping in the school's real content."""
import json
import re
import shutil
from pathlib import Path

import pytest

from scripts.check_kb import check_all

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def copy(tmp_path):
    """A copy of kb/ and config/ that a test may change."""
    shutil.copytree(ROOT / "kb", tmp_path / "kb")
    shutil.copytree(ROOT / "config", tmp_path / "config")
    return tmp_path


def problems(folder, demo_mode):
    return [f"{c.item}: {c.detail}" for c in check_all(folder / "kb", folder / "config", demo_mode) if not c.ok]


def make_real_looking(folder):
    """Remove every trace of demo content, as the real files would have."""
    for path in [*(folder / "kb").rglob("*.md"), *(folder / "kb").rglob("*.json"), folder / "config" / "working_days.json"]:
        text = path.read_text(encoding="utf-8")
        text = "\n".join(line for line in text.splitlines() if "DUMMY DATA" not in line)
        text = text.replace("DUMMY-0000", "AP-1234").replace("(DUMMY)", "")
        text = re.sub(r"@([\w-]+\.)*example\.com", "@school-pilot.in", text)
        text = re.sub(r"\+91 00000 0000(\d)", r"+91 98765 4321\1", text)
        if path.suffix == ".json":
            data = json.loads(text)
            data.pop("_note", None)
            text = json.dumps(data)
        path.write_text(text, encoding="utf-8")


def test_dummy_content_passes_in_demo_mode(copy):
    assert problems(copy, demo_mode=True) == []


def test_dummy_content_fails_when_demo_mode_is_off(copy):
    found = "\n".join(problems(copy, demo_mode=False))
    assert "kb/pilot-campus/fees.md: the word DUMMY" in found
    assert "kb/pilot-campus/contacts.md: the word DUMMY, an example.com address, a \"+91 00000\" phone number" in found
    assert "config/working_days.json" in found


def test_clean_content_passes_when_demo_mode_is_off(copy):
    make_real_looking(copy)
    assert problems(copy, demo_mode=False) == []


@pytest.mark.parametrize("word", ["an example.com address", "the word DUMMY", '"+91 00000" phone'])
def test_each_kind_of_leftover_is_caught(copy, word):
    make_real_looking(copy)
    extra = {"an example.com address": "Email: office@example.com",
             "the word DUMMY": "This is dummy text.",
             '"+91 00000" phone': "Call +91 00000 12345"}[word]
    faq = copy / "kb" / "pilot-campus" / "faq.md"
    faq.write_text(faq.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")
    [problem] = problems(copy, demo_mode=False)
    assert problem.startswith("Demo content left: kb/pilot-campus/faq.md")


def test_missing_file_and_missing_heading_are_reported(copy):
    (copy / "kb" / "pilot-campus" / "ptm.md").unlink()
    admissions = copy / "kb" / "pilot-campus" / "admissions.md"
    admissions.write_text(admissions.read_text(encoding="utf-8").replace("## Age criteria", "## Ages"), encoding="utf-8")
    found = problems(copy, demo_mode=True)
    assert "pilot-campus/ptm.md: file missing" in found
    assert "pilot-campus/admissions.md: missing: ## Age criteria" in found


def test_routing_must_match_escalation_md(copy):
    path = copy / "kb" / "pilot-campus" / "routing.json"
    routing = json.loads(path.read_text(encoding="utf-8"))
    routing["categories"][0]["name"] = "Studies"
    routing["categories"][1]["first"] = "Bursar"
    path.write_text(json.dumps(routing), encoding="utf-8")
    [problem] = problems(copy, demo_mode=True)
    assert "'Bursar', which is not in roles" in problem and "only in escalation.md: ['Academics']" in problem


def test_holidays_must_match_calendar_md(copy):
    calendar = copy / "kb" / "pilot-campus" / "calendar.md"
    calendar.write_text(calendar.read_text(encoding="utf-8").replace("Diwali 8 to 11", "Diwali 7 to 11"), encoding="utf-8")
    [problem] = problems(copy, demo_mode=True)
    assert "'Diwali' dates differ" in problem

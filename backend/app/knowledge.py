"""Loads the approved school content from kb/<campus>/*.md.
School facts live only in kb/, never in code."""
from pathlib import Path

KB_DIR = Path(__file__).resolve().parents[2] / "kb"


def load_campus(campus_dir: Path) -> str:
    """Join every .md file in one campus folder, each under a heading with its file name."""
    sections = []
    for md_file in sorted(campus_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8").strip()
        sections.append(f"=== File: {md_file.name} ===\n{text}")
    return "\n\n".join(sections)


def load_all_campuses() -> dict[str, str]:
    """Return {campus folder name: knowledge text} for every folder in kb/."""
    return {d.name: load_campus(d) for d in sorted(KB_DIR.iterdir()) if d.is_dir()}

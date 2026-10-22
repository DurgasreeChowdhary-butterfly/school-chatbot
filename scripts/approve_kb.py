"""Copy reviewed drafts (from scripts/ingest_docs.py) into kb/, but only when they are ready.

Usage:
    python scripts/approve_kb.py                 # all drafts in drafts/pilot-campus/ -> kb/pilot-campus/
    python scripts/approve_kb.py --dry-run       # only show what would happen
    python scripts/approve_kb.py --partial       # copy the files that are ready, leave the others

A draft is ready when it has no "NEEDS REVIEW" left and still has the headings the chatbot needs.
By default nothing is copied unless every draft is ready (so kb/ never mixes old and new content by accident).
The draft note and the "<!-- source: ... -->" comments are removed. The files being replaced are backed up to
drafts/_replaced/<date-time>/. Afterwards the content checker (scripts/check_kb.py) runs on kb/."""
import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check_kb import REQUIRED, check_all  # noqa: E402

MARK = "NEEDS REVIEW"


def problems_in(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = [f"line {n}: {MARK} left" for n, line in enumerate(text.splitlines(), 1)
             if MARK in line.upper() and not line.lstrip().startswith("> DRAFT")]  # the note is removed on copy
    lines = [l.strip().lower() for l in text.splitlines()]
    found += [f"heading '{h}' missing" for h in REQUIRED.get(path.name, [])
              if not any(l.startswith(h.lower()) for l in lines)]
    return found


def clean(text: str) -> str:
    """Remove the draft note and the source comments; tidy blank lines."""
    text = re.sub(r"\s*<!--.*?-->", "", text, flags=re.S)
    lines = [l.rstrip() for l in text.splitlines() if not l.lstrip().startswith("> DRAFT")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def approve(drafts: Path, kb: Path, partial: bool = False, dry_run: bool = False) -> tuple[list[str], dict]:
    """Returns (files copied, {file: problems})."""
    files = sorted(drafts.glob("*.md"))
    problems = {f.name: p for f in files if (p := problems_in(f))}
    problems.update({name: ["draft missing"] for name in REQUIRED if not (drafts / name).exists()})
    ready = [f for f in files if f.name not in problems]
    if problems and not partial:
        return [], problems
    if dry_run:
        return [f.name for f in ready], problems
    backup = drafts.parent / "_replaced" / datetime.now().strftime("%Y%m%d-%H%M%S")
    kb.mkdir(parents=True, exist_ok=True)
    for f in ready:
        target = kb / f.name
        if target.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup / f.name)
        target.write_text(clean(f.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    return [f.name for f in ready], problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drafts", default=str(ROOT / "drafts"))
    parser.add_argument("--kb", default=str(ROOT / "kb"))
    parser.add_argument("--campus", default="pilot-campus")
    parser.add_argument("--partial", action="store_true", help="copy the ready files even if others are not ready")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    drafts, kb = Path(args.drafts) / args.campus, Path(args.kb) / args.campus
    if not drafts.is_dir():
        print(f"No drafts in {drafts}. Run scripts/ingest_docs.py first.")
        return 1
    copied, problems = approve(drafts, kb, args.partial, args.dry_run)
    for name, items in sorted(problems.items()):
        print(f"  NOT READY  {name}: " + "; ".join(items[:5]) + (f" (+{len(items) - 5} more)" if len(items) > 5 else ""))
    if problems and not args.partial:
        print(f"\nNothing copied: {len(problems)} draft(s) not ready. Fix them (or use --partial).")
        return 1
    verb = "Would copy" if args.dry_run else "Copied"
    print(f"\n{verb} {len(copied)} file(s) to {kb}: {', '.join(copied) or 'none'}")
    if args.dry_run or not copied:
        return 1 if problems else 0

    print("\nContent check of kb/:")
    demo = os.getenv("DEMO_MODE", "true").strip().lower() in ("1", "true", "yes")
    results = check_all(Path(args.kb), ROOT / "config", demo)
    for r in results:
        if not r.ok:
            print(f"  FIX  {r.item}: {r.detail}")
    print("  All checks passed." if all(r.ok for r in results) else
          "  Fix the items above, then run python scripts/check_kb.py --live.")
    print("Next: update routing.json and config/working_days.json by hand, restart the server, run the tests.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

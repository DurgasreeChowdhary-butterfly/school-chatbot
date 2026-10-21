"""Print a saved answer-quality run so a person can judge it.
Usage: python scripts/show_results.py docs/test-runs/latest.json"""
import json
import sys

for r in json.load(open(sys.argv[1], encoding="utf-8")):
    print(f"[{r['id']}] Q: {r['question']}\n    EXPECTED: {r['expected']}\n    GOT: {r['reply']}\n")

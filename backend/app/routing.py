"""Reads kb/<campus>/routing.json: classes, who handles what, and reminder deadlines.
School facts live in kb/, never in code."""
import json
import os
from functools import lru_cache

from .knowledge import KB_DIR


@lru_cache
def load(campus: str) -> dict:
    return json.loads((KB_DIR / campus / "routing.json").read_text(encoding="utf-8"))


def classes(campus: str) -> list[str]:
    return load(campus)["classes"]


def role(campus: str, role_name: str) -> dict:
    """Contact details for a role, e.g. "Admission counsellor" -> {"name", "email", ...}."""
    info = dict(load(campus)["roles"][role_name])
    info["role"] = role_name
    # COUNSELLOR_EMAIL_<CAMPUS> in .env (e.g. COUNSELLOR_EMAIL_PILOT) overrides the counsellor's email.
    if role_name == load(campus)["counsellor"]:
        override = os.getenv(f"COUNSELLOR_EMAIL_{campus.split('-')[0].upper()}", "").strip()
        if override:
            info["email"] = override
    return info


def counsellor(campus: str) -> dict:
    return role(campus, load(campus)["counsellor"])


def front_office(campus: str) -> dict:
    return role(campus, load(campus)["front_office"])


def categories(campus: str) -> list[dict]:
    return load(campus)["categories"]


def category(campus: str, name: str) -> dict | None:
    for c in categories(campus):
        if c["name"].lower() == name.strip().lower():
            return c
    return None


def deadline(campus: str, key: str) -> int:
    """Working days allowed, e.g. deadline(campus, "ticket_escalation") -> 3."""
    return load(campus)["deadlines_in_working_days"][key]

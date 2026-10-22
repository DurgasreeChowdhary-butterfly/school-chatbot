"""Security headers on every response (see docs/security-review.md).

- Every response: no MIME sniffing, no framing (clickjacking), a careful Referer, no camera/microphone/location.
- Over HTTPS: HSTS, so browsers keep using HTTPS.
- Staff pages and the staff API: a strict Content-Security-Policy (only our own files, plus the staff page's one inline
  script, allowed by its hash) and no caching, because they show parents' details.
- Chat replies are not cached either (they can contain names and numbers)."""
import base64
import hashlib
import re
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware

PAGES = Path(__file__).resolve().parent / "staff_pages"


def _inline_script_hashes() -> str:
    hashes = []
    for page in PAGES.glob("*.html"):
        for script in re.findall(r"<script>(.*?)</script>", page.read_text(encoding="utf-8"), re.S):
            digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
            hashes.append(f"'sha256-{digest}'")
    return " ".join(hashes)


STAFF_CSP = ("default-src 'self'; script-src 'self' " + _inline_script_hashes() + "; style-src 'self' 'unsafe-inline'; "
             "img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; "
             "object-src 'none'")
NO_STORE_PATHS = ("/staff", "/chat", "/consent")


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.scheme == "https":
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        path = request.url.path
        if path.startswith("/staff"):
            h["Content-Security-Policy"] = STAFF_CSP
        if path.startswith(NO_STORE_PATHS):
            h["Cache-Control"] = "no-store"
        return response

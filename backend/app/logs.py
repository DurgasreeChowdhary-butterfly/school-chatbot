"""Logging setup. A filter masks anything that looks like an Indian mobile number in every log line,
so phone numbers never appear in logs in full."""
import logging
import re

from .validation import mask_mobile

# 10 digits starting 6-9, optionally with +91/91/0 in front and spaces or dashes inside.
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9](?:[\s-]?\d){9}(?!\d)")


def mask_phones(text: str) -> str:
    """Replace each phone number in the text with a masked version like 98******10."""
    return PHONE.sub(lambda m: mask_mobile(re.sub(r"\D", "", m.group())[-10:]), text)


class MaskPhoneFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = mask_phones(message)
        if masked != message:
            record.msg, record.args = masked, None
        return True


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    phone_filter = MaskPhoneFilter()
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, MaskPhoneFilter) for f in handler.filters):
                handler.addFilter(phone_filter)

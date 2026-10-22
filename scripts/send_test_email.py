"""Send ONE test email through the SMTP settings in .env to TEST_RECIPIENT, and explain any problem in plain words.

Usage:  python scripts/send_test_email.py
Needs in .env: SMTP_HOST, SMTP_PORT, SMTP_SECURITY (starttls / ssl / none), SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
and TEST_RECIPIENT (your own address). It uses the same sending code as the chatbot's outbox, so if this works,
the chatbot's emails will too. Nothing is sent to example.com or other placeholder addresses."""
import os
import smtplib
import socket
import ssl
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402


def settings_text() -> str:
    return (f"server {os.getenv('SMTP_HOST', '').strip() or '(empty)'}, port {os.getenv('SMTP_PORT', '').strip() or '587'}, "
            f"security {os.getenv('SMTP_SECURITY', 'starttls').strip() or 'starttls'}, "
            f"user {os.getenv('SMTP_USER', '').strip() or '(none)'}")


def explain(error: BaseException) -> str:
    """What went wrong and what to try, in plain words."""
    host = os.getenv("SMTP_HOST", "").strip()
    port = os.getenv("SMTP_PORT", "").strip() or "587"
    if isinstance(error, socket.gaierror):
        return (f"This computer cannot find the mail server '{host}'. Check the spelling of SMTP_HOST "
                f"(for example smtp.gmail.com or smtp.office365.com) and that the internet connection works.")
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return ("The mail server refused the username or password (SMTP_USER / SMTP_PASSWORD). Gmail and Microsoft 365 "
                "need an 'app password' (turn on 2-step verification, then create an app password) instead of the "
                "normal password. Some school accounts also need SMTP sending switched on by the IT admin.")
    if isinstance(error, smtplib.SMTPNotSupportedError):
        if "AUTH" in str(error).upper():
            return ("The mail server does not offer a login on this connection. Usually the security setting is wrong: "
                    "use SMTP_SECURITY=starttls with port 587, or ssl with port 465. If this server needs no login, "
                    "leave SMTP_USER empty.")
        return ("The mail server does not support STARTTLS on this port. Try SMTP_SECURITY=ssl with SMTP_PORT=465, "
                "or check the port your email provider gives.")
    if isinstance(error, ssl.SSLError):
        return (f"The secure connection failed on port {port}. The security setting probably does not match the port: "
                "port 465 needs SMTP_SECURITY=ssl, port 587 needs SMTP_SECURITY=starttls.")
    if isinstance(error, smtplib.SMTPSenderRefused):
        return ("The mail server refused the sender address (SMTP_FROM). Many providers only allow sending from the "
                "same address as SMTP_USER: set SMTP_FROM to that address, or leave it empty.")
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "The mail server refused the recipient (TEST_RECIPIENT). Check the address is typed correctly."
    if isinstance(error, smtplib.SMTPServerDisconnected):
        return ("The mail server closed the connection. This usually means the security setting does not match the "
                "port (465 = ssl, 587 = starttls), or the server blocked this computer.")
    if isinstance(error, (ConnectionRefusedError, TimeoutError, socket.timeout, ConnectionResetError)):
        return (f"Could not connect to {host} on port {port}. The port may be wrong (most providers use 587, some 465), "
                "or a firewall or the internet provider blocks outgoing email ports (common on home and school networks).")
    if isinstance(error, smtplib.SMTPResponseException):
        return (f"The mail server said no (code {error.smtp_code}): {error.smtp_error.decode(errors='replace') if isinstance(error.smtp_error, bytes) else error.smtp_error}. "
                "A 4xx code is temporary: try again later. A 5xx code needs a settings change or a call to the provider.")
    return f"Unexpected problem: {error!r}. Check every SMTP_ setting in .env."


def send_test() -> tuple[bool, str]:
    from backend.app import notify

    if not notify.smtp_configured():
        return False, "Email is not set up: put SMTP_HOST (and the other SMTP_ settings) in .env first."
    recipient = os.getenv("TEST_RECIPIENT", "").strip()
    if not recipient:
        return False, "TEST_RECIPIENT is empty in .env: put your own email address there."
    if notify.PLACEHOLDER.search(recipient):
        return False, f"{recipient} is a placeholder address; email is never sent to it. Use a real address you can read."
    if os.getenv("SMTP_USER", "").strip() and not os.getenv("SMTP_PASSWORD", "").strip():
        return False, "SMTP_USER is set but SMTP_PASSWORD is empty in .env."
    body = (f"This is a test email from the school chatbot, sent {datetime.now():%d %b %Y %H:%M}.\n"
            f"Settings used: {settings_text()}.\nIf you can read this, the chatbot's email works.")
    try:
        notify._send_email(recipient, "[School chatbot] Test email", body)
    except Exception as e:  # every kind of failure gets a plain explanation
        return False, explain(e)
    return True, f"Sent. Check the inbox (and the spam folder) of {recipient}."


def main() -> int:
    load_dotenv(ROOT / ".env")
    print(f"Sending a test email to {os.getenv('TEST_RECIPIENT', '').strip() or '(no TEST_RECIPIENT)'} "
          f"({settings_text()})...")
    ok, message = send_test()
    print(("OK: " if ok else "NOT SENT: ") + message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

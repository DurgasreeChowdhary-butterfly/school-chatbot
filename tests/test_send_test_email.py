"""scripts/send_test_email.py, tested only against the fake SMTP server (never a real one)."""
import smtplib
import socket
import ssl

import pytest

from scripts.send_test_email import explain, send_test
from tests.fake_smtp import FakeSMTPServer


@pytest.fixture
def smtp(monkeypatch):
    server = FakeSMTPServer()
    for key, value in {"SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(server.port), "SMTP_SECURITY": "none",
                       "SMTP_USER": "", "SMTP_PASSWORD": "", "TEST_RECIPIENT": "tester@school-pilot.in"}.items():
        monkeypatch.setenv(key, value)
    yield server
    server.stop()


def test_sends_one_email_to_the_test_recipient(smtp):
    ok, message = send_test()
    assert ok and "tester@school-pilot.in" in message
    [mail] = smtp.messages
    assert mail["to"] == ["tester@school-pilot.in"] and mail["subject"] == "[School chatbot] Test email"
    assert "SMTP_PASSWORD" not in mail["body"] and "Settings used" in mail["body"]


def test_settings_missing_or_unsafe(smtp, monkeypatch):
    monkeypatch.setenv("TEST_RECIPIENT", "me@example.com")
    assert "placeholder" in send_test()[1]
    monkeypatch.setenv("TEST_RECIPIENT", "")
    assert "TEST_RECIPIENT is empty" in send_test()[1]
    monkeypatch.setenv("TEST_RECIPIENT", "tester@school-pilot.in")
    monkeypatch.setenv("SMTP_USER", "chatbot@school-pilot.in")
    assert "SMTP_PASSWORD is empty" in send_test()[1]
    monkeypatch.setenv("SMTP_HOST", "")
    assert "not set up" in send_test()[1]
    assert smtp.messages == []


def test_server_errors_are_explained(smtp, monkeypatch):
    smtp.fail_next = 1
    ok, message = send_test()
    assert not ok and "code 451" in message and "temporary" in message
    monkeypatch.setenv("SMTP_USER", "chatbot@school-pilot.in")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    ok, message = send_test()   # the fake server offers no login
    assert not ok and "does not offer a login" in message
    monkeypatch.setenv("SMTP_PORT", "1")
    ok, message = send_test()   # nothing listens there
    assert not ok and "Could not connect" in message


def test_each_kind_of_error_has_plain_advice(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmial.com")
    assert "cannot find the mail server 'smtp.gmial.com'" in explain(socket.gaierror(11001, "getaddrinfo failed"))
    assert "app password" in explain(smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"))
    assert "465 needs SMTP_SECURITY=ssl" in explain(ssl.SSLError("wrong version number"))
    assert "SMTP_FROM" in explain(smtplib.SMTPSenderRefused(550, b"not allowed", "x@y"))
    assert "closed the connection" in explain(smtplib.SMTPServerDisconnected("Connection unexpectedly closed"))
    assert "STARTTLS" in explain(smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server."))

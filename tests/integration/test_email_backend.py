"""Coverage for the pluggable email backend (tw-qj9k).

Exercises both the ConsoleEmailBackend (default, in-memory outbox) and the
SmtpEmailBackend send path (with smtplib mocked — no real network), plus the
get_email_backend() factory's three resolution branches.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any
from unittest import mock

import pytest

from target_workspace.api.email import (
    ConsoleEmailBackend,
    SmtpEmailBackend,
    console_outbox,
    get_email_backend,
)

pytestmark = [pytest.mark.fast]

_SMTP_ENV_KEYS = (
    "TW_EMAIL_BACKEND",
    "TW_SMTP_HOST",
    "TW_SMTP_PORT",
    "TW_SMTP_USER",
    "TW_SMTP_PASSWORD",
    "TW_SMTP_FROM",
)


@pytest.fixture(autouse=True)
def _clean_email_env() -> Iterator[None]:
    """Snapshot + restore the SMTP env and clear the outbox per test."""
    saved = {k: os.environ.get(k) for k in _SMTP_ENV_KEYS}
    for k in _SMTP_ENV_KEYS:
        os.environ.pop(k, None)
    console_outbox().clear()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    console_outbox().clear()


def test_console_backend_captures_into_outbox() -> None:
    backend = ConsoleEmailBackend()
    backend.send(to="ops@example.com", subject="Alert", body="Target promoted")

    outbox = console_outbox()
    assert len(outbox) == 1
    assert outbox[0] == {
        "to": "ops@example.com",
        "subject": "Alert",
        "body": "Target promoted",
    }


def test_get_email_backend_defaults_to_console() -> None:
    backend = get_email_backend()
    assert isinstance(backend, ConsoleEmailBackend)
    assert backend.name == "console"


def test_get_email_backend_smtp_selected() -> None:
    os.environ["TW_EMAIL_BACKEND"] = "SMTP"  # case-insensitive
    backend = get_email_backend()
    assert isinstance(backend, SmtpEmailBackend)
    assert backend.name == "smtp"


def test_get_email_backend_unknown_raises() -> None:
    os.environ["TW_EMAIL_BACKEND"] = "carrier-pigeon"
    with pytest.raises(ValueError, match="unknown TW_EMAIL_BACKEND: carrier-pigeon"):
        get_email_backend()


def test_smtp_backend_raises_without_host() -> None:
    backend = SmtpEmailBackend()
    with pytest.raises(RuntimeError, match="TW_SMTP_HOST not configured"):
        backend.send(to="x@example.com", subject="s", body="b")


def test_smtp_backend_sends_with_auth() -> None:
    os.environ["TW_SMTP_HOST"] = "smtp.example.com"
    os.environ["TW_SMTP_PORT"] = "2525"
    os.environ["TW_SMTP_USER"] = "mailer"
    os.environ["TW_SMTP_PASSWORD"] = "secret"
    os.environ["TW_SMTP_FROM"] = "ops@example.com"

    fake_smtp = mock.MagicMock()
    ctx = fake_smtp.return_value.__enter__.return_value

    with mock.patch("target_workspace.api.email.smtplib.SMTP", fake_smtp):
        SmtpEmailBackend().send(
            to="recipient@example.com",
            subject="Promotion",
            body="COBRA-12 moved to FINISH",
        )

    fake_smtp.assert_called_once_with("smtp.example.com", 2525, timeout=10)
    ctx.starttls.assert_called_once_with()
    ctx.login.assert_called_once_with("mailer", "secret")
    ctx.send_message.assert_called_once()

    sent: Any = ctx.send_message.call_args.args[0]
    assert isinstance(sent, EmailMessage)
    assert sent["To"] == "recipient@example.com"
    assert sent["From"] == "ops@example.com"
    assert sent["Subject"] == "Promotion"
    assert "COBRA-12 moved to FINISH" in sent.get_content()


def test_smtp_backend_skips_login_without_credentials() -> None:
    os.environ["TW_SMTP_HOST"] = "smtp.example.com"
    # No user/password set, no explicit FROM → default sender path.

    fake_smtp = mock.MagicMock()
    ctx = fake_smtp.return_value.__enter__.return_value

    with mock.patch("target_workspace.api.email.smtplib.SMTP", fake_smtp):
        SmtpEmailBackend().send(to="r@example.com", subject="s", body="b")

    # Default port 587 used when TW_SMTP_PORT is unset.
    fake_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)
    ctx.starttls.assert_called_once_with()
    ctx.login.assert_not_called()
    ctx.send_message.assert_called_once()
    sent: Any = ctx.send_message.call_args.args[0]
    assert sent["From"] == "no-reply@example.com"

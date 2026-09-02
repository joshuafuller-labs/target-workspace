"""Pluggable email backend for transactional sends (tw-qj9k).

Backends:
  - ConsoleEmailBackend (default in dev/test) — captures messages in
    an in-memory list AND logs them to INFO. Used by tests.
  - SmtpEmailBackend — wired but disabled unless TW_SMTP_HOST is set.
    Production uses TW_EMAIL_BACKEND=smtp + the SMTP_* env vars.

The factory get_email_backend() returns the configured backend based
on TW_EMAIL_BACKEND (defaults to 'console').
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Protocol, runtime_checkable

_log = logging.getLogger(__name__)


@runtime_checkable
class EmailBackend(Protocol):
    """Send a single message; raise on configuration errors."""

    def send(self, *, to: str, subject: str, body: str) -> None: ...


# Module-level outbox used by ConsoleEmailBackend. Cleared by tests.
_outbox: list[dict[str, Any]] = []


def console_outbox() -> list[dict[str, Any]]:
    """Return the in-memory outbox (mutable list).

    Tests use this to inspect sent messages.
    """
    return _outbox


class ConsoleEmailBackend:
    """Capture into in-memory outbox + log at INFO. Default in dev/test."""

    name = "console"

    def send(self, *, to: str, subject: str, body: str) -> None:
        _outbox.append({"to": to, "subject": subject, "body": body})
        _log.info("[email/console] to=%s subject=%s body=%s", to, subject, body)


class SmtpEmailBackend:
    """Real SMTP backend. Requires TW_SMTP_HOST + TW_SMTP_FROM at minimum.

    Stubbed at MVP — wired but not enabled by default. Production sites
    set TW_EMAIL_BACKEND=smtp + the appropriate env vars.
    """

    name = "smtp"

    def send(self, *, to: str, subject: str, body: str) -> None:
        host = os.environ.get("TW_SMTP_HOST")
        if not host:
            msg = "TW_SMTP_HOST not configured"
            raise RuntimeError(msg)
        port = int(os.environ.get("TW_SMTP_PORT", "587"))
        user = os.environ.get("TW_SMTP_USER")
        pw = os.environ.get("TW_SMTP_PASSWORD")
        sender = os.environ.get("TW_SMTP_FROM", "no-reply@example.com")

        message = EmailMessage()
        message["From"] = sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            if user and pw:
                s.login(user, pw)
            s.send_message(message)


def get_email_backend() -> EmailBackend:
    """Resolve the configured backend. Default = console."""
    name = (os.environ.get("TW_EMAIL_BACKEND") or "console").lower()
    if name == "console":
        return ConsoleEmailBackend()
    if name == "smtp":
        return SmtpEmailBackend()
    msg = f"unknown TW_EMAIL_BACKEND: {name}"
    raise ValueError(msg)

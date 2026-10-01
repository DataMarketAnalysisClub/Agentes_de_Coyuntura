from datetime import datetime

import services.email_sender as email_sender
from app.config import Settings
from services.email_formatter import (
    UNSUBSCRIBE_URL_PLACEHOLDER,
    build_email_html,
    with_unsubscribe_link,
)
from services.email_sender import EmailSender
from storage.subscribers import Subscriber, SubscriberStatus


class FakeRepository:
    def __init__(self) -> None:
        self.saved = []

    def save(self, email) -> None:
        self.saved.append(email)


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass

    def starttls(self) -> None:
        pass

    def login(self, user, password) -> None:
        pass

    def send_message(self, message) -> None:
        FakeSMTP.sent.append(message)


SMTP_SETTINGS = dict(
    dry_run=False,
    smtp_user="bot@example.com",
    smtp_password="secret",
    email_from="bot@example.com",
    email_to="club@example.com",
    email_cc="cc@example.com",
)


def test_recipients_override_replaces_club_list(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    repository = FakeRepository()
    sender = EmailSender(Settings(**SMTP_SETTINGS), repository)

    assert sender.send("Ops", "texto", "<p>html</p>", True, recipients=["ops@example.com"])

    message = FakeSMTP.sent[0]
    assert message["To"] == "ops@example.com"
    assert message["Cc"] is None
    assert repository.saved[0].recipients == "ops@example.com"


def test_default_recipients_use_club_list(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    sender = EmailSender(Settings(**SMTP_SETTINGS), FakeRepository())

    assert sender.send("Brief", "texto", "<p>html</p>", True)

    assert FakeSMTP.sent[0]["To"] == "club@example.com"
    assert FakeSMTP.sent[0]["Cc"] == "cc@example.com"


def test_logo_is_embedded_as_related_part_and_from_has_display_name(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    sender = EmailSender(Settings(**SMTP_SETTINGS), FakeRepository())

    assert sender.send("Brief", "texto", '<img src="cid:dmac-logo" alt="DMAC">', True)

    message = FakeSMTP.sent[0]
    assert message["From"] == "DMAC Brief · Nix <bot@example.com>"
    assert message.get_content_type() == "multipart/alternative"
    text_part, related = message.get_payload()
    assert text_part.get_content_type() == "text/plain"
    assert related.get_content_type() == "multipart/related"
    html_part, logo = related.get_payload()
    assert html_part.get_content_type() == "text/html"
    assert logo.get_content_type() == "image/png"
    assert logo["Content-ID"] == "<dmac-logo>"
    assert logo.get_content_disposition() == "inline"
    assert logo.get_payload(decode=True).startswith(b"\x89PNG")


def test_html_without_logo_reference_is_not_multipart_related(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    settings = Settings(**{**SMTP_SETTINGS, "email_from": "Club DMAC <bot@example.com>"})

    assert EmailSender(settings, FakeRepository()).send("Ops", "texto", "<p>html</p>", True)

    message = FakeSMTP.sent[0]
    assert message["From"] == "Club DMAC <bot@example.com>"
    assert [part.get_content_type() for part in message.get_payload()] == ["text/plain", "text/html"]


# --- Mailing con suscripcion -------------------------------------------------

MAILING_SETTINGS = dict(SMTP_SETTINGS, mailing_enabled=True, mailing_public_url="https://dmac.example.ts.net")


def _subscriber(sid: int, email: str) -> Subscriber:
    now = datetime(2026, 9, 30, 12, 0)
    return Subscriber(sid, email, SubscriberStatus.ACTIVE, f"{'tok' * 11}{sid}", "web", now, now)


class FakeSubscribers:
    def __init__(self, subscribers=None, error: Exception | None = None) -> None:
        self.subscribers = subscribers or []
        self.error = error

    def active(self):
        if self.error:
            raise self.error
        return self.subscribers


def _html() -> str:
    return build_email_html("DMAC Brief · 30 sep", "Texto del brief")


def test_mailing_sends_one_personal_message_per_active_subscriber(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    repository = FakeRepository()
    subscribers = FakeSubscribers([_subscriber(1, "ana@udd.cl"), _subscriber(2, "beto@gmail.com")])
    sender = EmailSender(Settings(**MAILING_SETTINGS), repository, subscribers=subscribers)

    assert sender.send("Brief", "texto", _html(), True)

    assert [m["To"] for m in FakeSMTP.sent] == ["ana@udd.cl", "beto@gmail.com"]
    first = FakeSMTP.sent[0]
    url = f"https://dmac.example.ts.net/baja?t={'tok' * 11}1"
    assert first["Cc"] is None
    assert first["List-Unsubscribe"] == f"<{url}>"
    assert first["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    text_part, html_part = first.get_payload()
    assert f"Cancelar suscripción: {url}" in text_part.get_content()
    html = html_part.get_content()
    assert f'href="{url}"' in html
    assert UNSUBSCRIBE_URL_PLACEHOLDER not in html
    assert [(r.recipients, r.status) for r in repository.saved] == [
        ("ana@udd.cl", "sent"), ("beto@gmail.com", "sent"),
    ]


def test_mailing_failure_for_one_subscriber_does_not_stop_the_rest(monkeypatch) -> None:
    class FlakySMTP(FakeSMTP):
        def send_message(self, message) -> None:
            if message["To"] == "ana@udd.cl":
                raise email_sender.smtplib.SMTPRecipientsRefused({"ana@udd.cl": (550, b"no")})
            super().send_message(message)

    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FlakySMTP)
    repository = FakeRepository()
    subscribers = FakeSubscribers([_subscriber(1, "ana@udd.cl"), _subscriber(2, "beto@gmail.com")])

    assert EmailSender(Settings(**MAILING_SETTINGS), repository, subscribers=subscribers).send(
        "Brief", "texto", _html(), True
    )
    assert [m["To"] for m in FakeSMTP.sent] == ["beto@gmail.com"]
    assert [r.status for r in repository.saved] == ["error", "sent"]


def test_mailing_falls_back_to_email_to_when_mysql_fails(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    subscribers = FakeSubscribers(error=ConnectionError("mysql down"))

    assert EmailSender(Settings(**MAILING_SETTINGS), FakeRepository(), subscribers=subscribers).send(
        "Brief", "texto", _html(), True
    )
    message = FakeSMTP.sent[0]
    assert message["To"] == "club@example.com"
    assert message["List-Unsubscribe"] is None
    assert "Cancelar suscripción" not in message.get_payload()[1].get_content()


def test_mailing_without_public_url_falls_back_to_email_to(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    settings = Settings(**{**MAILING_SETTINGS, "mailing_public_url": ""})
    subscribers = FakeSubscribers([_subscriber(1, "ana@udd.cl")])

    assert EmailSender(settings, FakeRepository(), subscribers=subscribers).send("Brief", "texto", _html(), True)
    assert [m["To"] for m in FakeSMTP.sent] == ["club@example.com"]


def test_explicit_recipients_never_use_the_subscriber_list(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    subscribers = FakeSubscribers([_subscriber(1, "ana@udd.cl")])

    assert EmailSender(Settings(**MAILING_SETTINGS), FakeRepository(), subscribers=subscribers).send(
        "Ops", "texto", _html(), True, recipients=["ops@example.com"]
    )
    assert [m["To"] for m in FakeSMTP.sent] == ["ops@example.com"]
    assert "Cancelar suscripción" not in FakeSMTP.sent[0].get_payload()[1].get_content()


def test_mailing_dry_run_sends_nothing(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    repository = FakeRepository()
    settings = Settings(**{**MAILING_SETTINGS, "dry_run": True})
    subscribers = FakeSubscribers([_subscriber(1, "ana@udd.cl")])

    assert not EmailSender(settings, repository, subscribers=subscribers).send("Brief", "texto", _html(), True)
    assert FakeSMTP.sent == []
    assert (repository.saved[0].recipients, repository.saved[0].status) == ("1 suscriptores activos", "dry_run")


def test_club_list_email_has_no_unsubscribe_block() -> None:
    html = _html()
    assert UNSUBSCRIBE_URL_PLACEHOLDER in html
    stripped = with_unsubscribe_link(html, None)
    assert "Cancelar suscripción" not in stripped
    assert "dmac-unsubscribe" not in stripped
    assert "Nix Assistant, DMAC UDD" in stripped


def test_mailing_with_no_active_subscribers_sends_nothing(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    repository = FakeRepository()

    assert not EmailSender(Settings(**MAILING_SETTINGS), repository, subscribers=FakeSubscribers([])).send(
        "Brief", "texto", _html(), True
    )
    assert FakeSMTP.sent == []
    assert repository.saved[0].status == "skipped"


def test_brief_invites_forwarded_readers_to_subscribe(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    settings = Settings(**{**SMTP_SETTINGS, "mailing_public_url": "https://dmac.example.ts.net/"})

    assert EmailSender(settings, FakeRepository()).send("Brief", "texto", _html(), True)

    text_part, html_part = FakeSMTP.sent[0].get_payload()
    html = html_part.get_content()
    assert "¿Te reenviaron este correo?" in html
    assert 'href="https://dmac.example.ts.net"' in html
    assert "%%DMAC_SUBSCRIBE_URL%%" not in html
    assert "Suscríbete a DMAC Brief: https://dmac.example.ts.net" in text_part.get_content()


def test_subscriber_copies_also_carry_the_subscribe_invite(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    subscribers = FakeSubscribers([_subscriber(1, "ana@udd.cl")])

    assert EmailSender(Settings(**MAILING_SETTINGS), FakeRepository(), subscribers=subscribers).send(
        "Brief", "texto", _html(), True
    )
    html = FakeSMTP.sent[0].get_payload()[1].get_content()
    assert 'href="https://dmac.example.ts.net"' in html
    assert "Cancelar suscripción" in html


def test_no_subscribe_invite_without_public_url_or_in_ops_emails(monkeypatch) -> None:
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    with_url = Settings(**{**SMTP_SETTINGS, "mailing_public_url": "https://dmac.example.ts.net"})

    assert EmailSender(Settings(**SMTP_SETTINGS), FakeRepository()).send("Brief", "texto", _html(), True)
    assert EmailSender(with_url, FakeRepository()).send("Ops", "t", _html(), True, recipients=["ops@x.cl"])

    for message in FakeSMTP.sent:
        text_part, html_part = message.get_payload()
        assert "reenviaron" not in html_part.get_content()
        assert "dmac-subscribe" not in html_part.get_content()
        assert "reenviaron" not in text_part.get_content()

import services.email_sender as email_sender
from app.config import Settings
from services.email_sender import EmailSender


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

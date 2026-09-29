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

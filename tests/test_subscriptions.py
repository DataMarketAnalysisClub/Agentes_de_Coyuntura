from datetime import datetime, timedelta

import pytest

from app.config import Settings
from services.subscriptions import (
    ConfirmOutcome,
    SubscribeOutcome,
    SubscriptionService,
    UnsubscribeOutcome,
    normalize_email,
)
from storage.subscribers import DuplicateSubscriberError, SubscriberEvent, SubscriberStatus

PUBLIC_URL = "https://dmac.example.ts.net"


class FakeSender:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.sent = []

    def send(self, subject, text_body, html_body, enabled, recipients=None):
        self.sent.append({"subject": subject, "text": text_body, "html": html_body, "recipients": recipients})
        return self.result


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 30, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def sender():
    return FakeSender()


@pytest.fixture
def service(subscriber_repository, sender, clock):
    settings = Settings(mailing_public_url=PUBLIC_URL + "/", email_enabled=True)
    return SubscriptionService(subscriber_repository, settings, sender=sender, clock=clock)


def _token_from(sent) -> str:
    return sent["text"].split("?t=", 1)[1].split()[0]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Ana.Perez@UDD.cl ", "ana.perez@udd.cl"),
        ("ana+brief@gmail.com", "ana+brief@gmail.com"),
        ("sin-arroba.cl", None),
        ("ana@localhost", None),
        ("ana..perez@udd.cl", None),
        ("ana@udd.cl\nBcc: x@y.cl", None),
        ("", None),
        (None, None),
        ("a" * 65 + "@udd.cl", None),
    ],
)
def test_normalize_email(raw, expected) -> None:
    assert normalize_email(raw) == expected


def test_subscribe_creates_pending_and_sends_confirmation_link(service, subscriber_repository, sender) -> None:
    assert service.subscribe("Ana@UDD.cl") is SubscribeOutcome.CONFIRMATION_SENT

    subscriber = subscriber_repository.get_by_email("ana@udd.cl")
    assert subscriber.status is SubscriberStatus.PENDING
    assert subscriber.confirmation_sent_at is not None
    assert sender.sent[0]["recipients"] == ["ana@udd.cl"]
    assert f"{PUBLIC_URL}/confirmar?t={subscriber.token}" in sender.sent[0]["text"]
    assert f"{PUBLIC_URL}/confirmar?t={subscriber.token}" in sender.sent[0]["html"]


def test_invalid_email_is_rejected_without_writing(service, subscriber_repository, sender) -> None:
    assert service.subscribe("no-es-correo") is SubscribeOutcome.INVALID_EMAIL
    assert subscriber_repository.find() == []
    assert sender.sent == []


def test_confirm_activates_and_is_idempotent(service, subscriber_repository, sender) -> None:
    service.subscribe("ana@udd.cl")
    token = _token_from(sender.sent[0])

    assert service.confirm(token) is ConfirmOutcome.CONFIRMED
    assert service.confirm(token) is ConfirmOutcome.ALREADY_ACTIVE
    assert [s.email for s in subscriber_repository.active()] == ["ana@udd.cl"]


def test_confirm_rejects_unknown_malformed_and_expired_tokens(service, sender, clock) -> None:
    assert service.confirm("x" * 43) is ConfirmOutcome.INVALID
    assert service.confirm("corto") is ConfirmOutcome.INVALID
    assert service.confirm(None) is ConfirmOutcome.INVALID

    service.subscribe("ana@udd.cl")
    clock.advance(days=8)
    assert service.confirm(_token_from(sender.sent[0])) is ConfirmOutcome.EXPIRED


def test_resend_is_throttled_then_reuses_the_same_link(service, sender, clock) -> None:
    service.subscribe("ana@udd.cl")
    assert service.subscribe("ana@udd.cl") is SubscribeOutcome.THROTTLED
    assert len(sender.sent) == 1

    clock.advance(minutes=11)
    assert service.subscribe("ana@udd.cl") is SubscribeOutcome.CONFIRMATION_SENT
    assert _token_from(sender.sent[1]) == _token_from(sender.sent[0])


def test_expired_pending_gets_a_new_token_on_resubscribe(service, sender, clock) -> None:
    service.subscribe("ana@udd.cl")
    clock.advance(days=8)

    assert service.subscribe("ana@udd.cl") is SubscribeOutcome.CONFIRMATION_SENT
    assert _token_from(sender.sent[1]) != _token_from(sender.sent[0])
    assert service.confirm(_token_from(sender.sent[1])) is ConfirmOutcome.CONFIRMED


def test_active_subscriber_gets_no_new_email(service, sender) -> None:
    service.subscribe("ana@udd.cl")
    service.confirm(_token_from(sender.sent[0]))

    assert service.subscribe("ana@udd.cl") is SubscribeOutcome.ALREADY_ACTIVE
    assert len(sender.sent) == 1


def test_unsubscribe_is_idempotent_and_blocks_old_confirmation(service, subscriber_repository, sender) -> None:
    service.subscribe("ana@udd.cl")
    token = _token_from(sender.sent[0])
    service.confirm(token)

    assert service.unsubscribe(token) is UnsubscribeOutcome.UNSUBSCRIBED
    assert service.unsubscribe(token) is UnsubscribeOutcome.ALREADY_UNSUBSCRIBED
    assert service.confirm(token) is ConfirmOutcome.INVALID
    assert subscriber_repository.active() == []
    assert service.unsubscribe("y" * 43) is UnsubscribeOutcome.INVALID


def test_pending_can_unsubscribe_before_confirming(service, subscriber_repository, sender) -> None:
    service.subscribe("ana@udd.cl")

    assert service.unsubscribe(_token_from(sender.sent[0])) is UnsubscribeOutcome.UNSUBSCRIBED
    assert subscriber_repository.get_by_email("ana@udd.cl").status is SubscriberStatus.UNSUBSCRIBED


def test_resubscribe_after_unsubscribe_rotates_token(service, subscriber_repository, sender) -> None:
    service.subscribe("ana@udd.cl")
    old_token = _token_from(sender.sent[0])
    service.confirm(old_token)
    service.unsubscribe(old_token)

    assert service.subscribe("ana@udd.cl") is SubscribeOutcome.CONFIRMATION_SENT
    new_token = _token_from(sender.sent[1])
    assert new_token != old_token
    assert service.unsubscribe(old_token) is UnsubscribeOutcome.INVALID
    assert subscriber_repository.active() == []
    assert service.confirm(new_token) is ConfirmOutcome.CONFIRMED


def test_hourly_cap_stops_confirmation_emails(subscriber_repository, sender, clock) -> None:
    settings = Settings(mailing_public_url=PUBLIC_URL, email_enabled=True, mailing_confirm_max_per_hour=2)
    service = SubscriptionService(subscriber_repository, settings, sender=sender, clock=clock)

    assert service.subscribe("a@udd.cl") is SubscribeOutcome.CONFIRMATION_SENT
    assert service.subscribe("b@udd.cl") is SubscribeOutcome.CONFIRMATION_SENT
    assert service.subscribe("c@udd.cl") is SubscribeOutcome.THROTTLED
    assert len(sender.sent) == 2

    clock.advance(minutes=61)
    assert service.subscribe("c@udd.cl") is SubscribeOutcome.CONFIRMATION_SENT


def test_failed_confirmation_email_is_not_marked_sent(subscriber_repository, clock) -> None:
    settings = Settings(mailing_public_url=PUBLIC_URL, email_enabled=True)
    service = SubscriptionService(subscriber_repository, settings, sender=FakeSender(result=False), clock=clock)

    assert service.subscribe("ana@udd.cl") is SubscribeOutcome.SEND_FAILED
    assert subscriber_repository.get_by_email("ana@udd.cl").confirmation_sent_at is None
    assert subscriber_repository.count_events_since(SubscriberEvent.CONFIRMATION_SENT, clock.now) == 0


def test_admin_add_remove_and_erase(service, subscriber_repository, sender) -> None:
    subscriber = service.add_active("DMAC@udd.cl")
    assert subscriber.status is SubscriberStatus.ACTIVE
    assert subscriber.source == "admin"
    assert sender.sent == []

    assert service.remove("dmac@udd.cl") is UnsubscribeOutcome.UNSUBSCRIBED
    assert service.add_active("dmac@udd.cl").status is SubscriberStatus.ACTIVE
    assert service.erase("dmac@udd.cl") is True
    assert subscriber_repository.get_by_email("dmac@udd.cl") is None
    assert service.erase("dmac@udd.cl") is False


def test_repository_rejects_duplicate_email(subscriber_repository, clock) -> None:
    subscriber_repository.create("ana@udd.cl", "t" * 43, "web", clock.now)
    with pytest.raises(DuplicateSubscriberError):
        subscriber_repository.create("ana@udd.cl", "u" * 43, "web", clock.now)


def test_repository_counts_and_audit_events(service, subscriber_repository, sender, clock) -> None:
    service.subscribe("a@udd.cl")
    service.subscribe("b@udd.cl")
    service.confirm(_token_from(sender.sent[0]))

    assert subscriber_repository.counts_by_status() == {"pending": 1, "active": 1, "unsubscribed": 0}
    since = clock.now - timedelta(minutes=1)
    assert subscriber_repository.count_events_since(SubscriberEvent.SUBSCRIBE_REQUESTED, since) == 2
    assert subscriber_repository.count_events_since(SubscriberEvent.CONFIRMED, since) == 1

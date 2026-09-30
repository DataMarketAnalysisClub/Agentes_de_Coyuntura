"""Altas y bajas del mailing con doble confirmacion.

Flujo:
- `subscribe`: fila `pending` con token aleatorio y correo con el link de
  confirmacion. Responde lo mismo exista o no el correo (no revela quien esta
  inscrito).
- `confirm`: `pending` -> `active` si el link no vencio.
- `unsubscribe`: cualquier estado -> `unsubscribed`; idempotente. Lo usan el
  link del pie y el boton "Cancelar suscripcion" de Gmail/Outlook (RFC 8058).

El token sirve para confirmar y para darse de baja; cambia en cada
reinscripcion, asi que un link viejo de confirmacion no reactiva a nadie.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from html import escape

from app.config import Settings, get_settings
from storage.subscribers import (
    DuplicateSubscriberError,
    Subscriber,
    SubscriberEvent,
    SubscriberRepository,
    SubscriberStatus,
)

logger = logging.getLogger(__name__)

# Suficiente para rechazar basura; la doble confirmacion prueba que existe.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


class SubscribeOutcome(StrEnum):
    CONFIRMATION_SENT = "confirmation_sent"
    ALREADY_ACTIVE = "already_active"
    THROTTLED = "throttled"
    INVALID_EMAIL = "invalid_email"
    SEND_FAILED = "send_failed"


class ConfirmOutcome(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_ACTIVE = "already_active"
    EXPIRED = "expired"
    INVALID = "invalid"


class UnsubscribeOutcome(StrEnum):
    UNSUBSCRIBED = "unsubscribed"
    ALREADY_UNSUBSCRIBED = "already_unsubscribed"
    INVALID = "invalid"


def normalize_email(raw: str | None) -> str | None:
    """Correo en minusculas y sin espacios, o None si no es valido."""
    email = (raw or "").strip().lower()
    if not email or len(email) > 254 or not _EMAIL_RE.fullmatch(email):
        return None
    if len(email.split("@", 1)[0]) > 64 or ".." in email:
        return None
    return email


def is_well_formed_token(token: str | None) -> bool:
    return bool(token and _TOKEN_RE.fullmatch(token))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _utcnow() -> datetime:
    # MySQL DATETIME no guarda zona: todo en UTC sin tzinfo.
    return datetime.now(UTC).replace(tzinfo=None)


class SubscriptionService:
    def __init__(
        self,
        repository: SubscriberRepository,
        settings: Settings | None = None,
        sender=None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self._sender = sender
        self._clock = clock

    @property
    def sender(self):
        if self._sender is None:
            from services.email_sender import EmailSender

            self._sender = EmailSender(self.settings)
        return self._sender

    # --- Links ------------------------------------------------------------

    def _url(self, path: str, token: str) -> str:
        return f"{self.settings.mailing_public_url.rstrip('/')}/{path}?t={token}"

    def confirm_url(self, token: str) -> str:
        return self._url("confirmar", token)

    def unsubscribe_url(self, token: str) -> str:
        return self._url("baja", token)

    # --- Casos de uso -----------------------------------------------------

    def subscribe(self, raw_email: str | None, source: str = "web") -> SubscribeOutcome:
        email = normalize_email(raw_email)
        if email is None:
            return SubscribeOutcome.INVALID_EMAIL
        now = self._clock()
        subscriber = self.repository.get_by_email(email)

        if subscriber is not None and subscriber.status is SubscriberStatus.ACTIVE:
            logger.info("Subscribe request for an active subscriber", extra={"subscriber_id": subscriber.id})
            return SubscribeOutcome.ALREADY_ACTIVE

        if subscriber is not None and subscriber.status is SubscriberStatus.PENDING:
            sent_at = subscriber.confirmation_sent_at
            resend_after = timedelta(minutes=self.settings.mailing_confirm_resend_minutes)
            if sent_at is not None and now - sent_at < resend_after:
                return SubscribeOutcome.THROTTLED
            if self._confirmation_expired(subscriber, now):
                self.repository.restart_pending(subscriber.id, new_token(), source, now)
                subscriber = self.repository.get_by_email(email)
        elif subscriber is not None:  # unsubscribed: reinscripcion con token nuevo
            self.repository.restart_pending(subscriber.id, new_token(), source, now)
            subscriber = self.repository.get_by_email(email)
        else:
            try:
                subscriber = self.repository.create(email, new_token(), source, now)
            except DuplicateSubscriberError:
                # Dos envios simultaneos del formulario: el otro ya la creo.
                return SubscribeOutcome.THROTTLED

        self.repository.add_event(subscriber.id, SubscriberEvent.SUBSCRIBE_REQUESTED, now, source)
        if self._hourly_cap_reached(now):
            logger.warning("Confirmation email hourly cap reached", extra={"subscriber_id": subscriber.id})
            return SubscribeOutcome.THROTTLED
        return self._send_confirmation(subscriber, now)

    def confirm(self, token: str | None) -> ConfirmOutcome:
        subscriber = self._by_token(token)
        if subscriber is None or subscriber.status is SubscriberStatus.UNSUBSCRIBED:
            return ConfirmOutcome.INVALID
        if subscriber.status is SubscriberStatus.ACTIVE:
            return ConfirmOutcome.ALREADY_ACTIVE
        now = self._clock()
        if self._confirmation_expired(subscriber, now):
            return ConfirmOutcome.EXPIRED
        self.repository.activate(subscriber.id, now)
        self.repository.add_event(subscriber.id, SubscriberEvent.CONFIRMED, now)
        logger.info("Subscriber confirmed", extra={"subscriber_id": subscriber.id})
        return ConfirmOutcome.CONFIRMED

    def unsubscribe(self, token: str | None, detail: str = "link") -> UnsubscribeOutcome:
        subscriber = self._by_token(token)
        if subscriber is None:
            return UnsubscribeOutcome.INVALID
        if subscriber.status is SubscriberStatus.UNSUBSCRIBED:
            return UnsubscribeOutcome.ALREADY_UNSUBSCRIBED
        now = self._clock()
        self.repository.unsubscribe(subscriber.id, now)
        self.repository.add_event(subscriber.id, SubscriberEvent.UNSUBSCRIBED, now, detail)
        logger.info("Subscriber unsubscribed", extra={"subscriber_id": subscriber.id, "via": detail})
        return UnsubscribeOutcome.UNSUBSCRIBED

    # --- Administracion (CLI) ---------------------------------------------

    def add_active(self, raw_email: str) -> Subscriber:
        """Alta directa sin confirmacion (solo mantenedores, con consentimiento)."""
        email = normalize_email(raw_email)
        if email is None:
            raise ValueError("Correo invalido")
        now = self._clock()
        subscriber = self.repository.get_by_email(email)
        if subscriber is None:
            subscriber = self.repository.create(email, new_token(), "admin", now, SubscriberStatus.ACTIVE)
        elif subscriber.status is not SubscriberStatus.ACTIVE:
            if subscriber.status is SubscriberStatus.UNSUBSCRIBED:
                self.repository.restart_pending(subscriber.id, new_token(), "admin", now)
            self.repository.activate(subscriber.id, now)
            subscriber = self.repository.get_by_email(email)
        self.repository.add_event(subscriber.id, SubscriberEvent.ADDED_BY_ADMIN, now)
        return subscriber

    def remove(self, raw_email: str) -> UnsubscribeOutcome:
        subscriber = self.repository.get_by_email(normalize_email(raw_email) or "")
        if subscriber is None:
            return UnsubscribeOutcome.INVALID
        return self.unsubscribe(subscriber.token, detail="admin")

    def erase(self, raw_email: str) -> bool:
        subscriber = self.repository.get_by_email(normalize_email(raw_email) or "")
        if subscriber is None:
            return False
        self.repository.delete(subscriber.id)
        return True

    # --- Internos ---------------------------------------------------------

    def _by_token(self, token: str | None) -> Subscriber | None:
        if not is_well_formed_token(token):
            return None
        return self.repository.get_by_token(token)

    def _confirmation_expired(self, subscriber: Subscriber, now: datetime) -> bool:
        started = subscriber.confirmation_sent_at or subscriber.updated_at
        return now - started > timedelta(days=self.settings.mailing_confirm_ttl_days)

    def _hourly_cap_reached(self, now: datetime) -> bool:
        sent = self.repository.count_events_since(SubscriberEvent.CONFIRMATION_SENT, now - timedelta(hours=1))
        return sent >= self.settings.mailing_confirm_max_per_hour

    def _send_confirmation(self, subscriber: Subscriber, now: datetime) -> SubscribeOutcome:
        subject, text_body, html_body = confirmation_email(self.confirm_url(subscriber.token))
        sent = self.sender.send(
            subject, text_body, html_body, self.settings.email_enabled, recipients=[subscriber.email]
        )
        if not sent:
            logger.warning("Confirmation email not sent", extra={"subscriber_id": subscriber.id})
            return SubscribeOutcome.SEND_FAILED
        self.repository.mark_confirmation_sent(subscriber.id, now)
        self.repository.add_event(subscriber.id, SubscriberEvent.CONFIRMATION_SENT, now)
        return SubscribeOutcome.CONFIRMATION_SENT


def confirmation_email(confirm_url: str) -> tuple[str, str, str]:
    """Asunto, texto y HTML del correo de confirmacion (sin link de baja)."""
    subject = "Confirma tu suscripción a DMAC Brief"
    text_body = (
        "Hola:\n\n"
        "Recibimos una solicitud para inscribir este correo en DMAC Brief, el resumen de"
        " coyuntura financiera del Data Market Analysis Club UDD.\n\n"
        f"Para confirmar, abre este enlace:\n{confirm_url}\n\n"
        "Si no fuiste tú, ignora este mensaje: sin confirmación no te enviaremos nada.\n"
    )
    url = escape(confirm_url, quote=True)
    html_body = (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"></head>"
        "<body style=\"margin:0;padding:24px 12px;background:#f4f4f1;"
        "font-family:Georgia,'Times New Roman',serif;color:#1a1a1a;\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\">"
        "<tr><td align=\"center\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        " style=\"max-width:560px;background:#ffffff;border:1px solid #d9d9d4;\">"
        "<tr><td style=\"padding:28px 28px 8px 28px;font-size:28px;font-weight:700;\">DMAC Brief</td></tr>"
        "<tr><td style=\"padding:8px 28px;font-family:Arial,sans-serif;font-size:15px;line-height:1.6;\">"
        "<p>Recibimos una solicitud para inscribir este correo en <strong>DMAC Brief</strong>,"
        " el resumen de coyuntura financiera del Data Market Analysis Club UDD.</p>"
        f"<p style=\"margin:24px 0;\"><a href=\"{url}\" style=\"background:#1a1a1a;color:#ffffff;"
        "padding:12px 22px;text-decoration:none;font-weight:700;display:inline-block;\">"
        "Confirmar suscripción</a></p>"
        f"<p style=\"font-size:13px;color:#5c5c58;\">Si el botón no funciona, copia este enlace:<br>{url}</p>"
        "<p style=\"font-size:13px;color:#5c5c58;\">Si no fuiste tú, ignora este mensaje:"
        " sin confirmación no te enviaremos nada.</p>"
        "</td></tr>"
        "<tr><td style=\"padding:8px 28px 24px 28px;font-family:Arial,sans-serif;font-size:12px;color:#5c5c58;\">"
        "Data Market Analysis Club UDD</td></tr>"
        "</table></td></tr></table></body></html>"
    )
    return subject, text_body, html_body

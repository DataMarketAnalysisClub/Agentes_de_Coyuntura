import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from app.config import Settings, get_settings
from services.email_formatter import (
    text_with_subscribe_link,
    text_with_unsubscribe_link,
    with_subscribe_link,
    with_unsubscribe_link,
)
from storage.models import SentEmail
from storage.repositories import SentEmailRepository

logger = logging.getLogger(__name__)

# Content-ID del logo embebido; el HTML lo referencia como src="cid:dmac-logo".
LOGO_CID = "dmac-logo"


class EmailSender:
    """SMTP email sender with dry-run and audit logging support."""

    def __init__(
        self,
        settings: Settings | None = None,
        repository: SentEmailRepository | None = None,
        subscribers=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or SentEmailRepository()
        # SubscriberRepository (MySQL); se crea al primer envio con mailing.
        self._subscribers = subscribers

    def send(
        self,
        subject: str,
        text_body: str,
        html_body: str,
        enabled: bool,
        inline_images: dict[str, bytes] | None = None,
        recipients: list[str] | None = None,
    ) -> bool:
        """Send the email via SMTP.

        `inline_images` is accepted for backward compatibility but ignored.
        The only embedded image is the logo (`cid:dmac-logo`, see
        `_embed_logo`); charts are HTML/CSS.

        `recipients` overrides EMAIL_TO/EMAIL_CC (e.g. operational alerts that
        must never reach the club mailing list).

        With MAILING_ENABLED and no `recipients`, the email goes to every
        `active` subscriber (MySQL), one message each with a personal
        unsubscribe link. If the subscriber list can't be read, it falls back
        to EMAIL_TO/EMAIL_CC.
        """
        del inline_images  # deprecated: HTML is self-contained now
        # Invitacion "¿Te reenviaron este correo?" solo en el brief (sin
        # `recipients`) y con URL publica; nunca en avisos ni pruebas.
        subscribe_url = self.settings.mailing_public_url.rstrip("/") if recipients is None else ""
        html_body = with_subscribe_link(html_body, subscribe_url or None)
        text_body = text_with_subscribe_link(text_body, subscribe_url or None)
        if recipients is None and self.settings.mailing_enabled:
            subscribers = self._load_subscribers()
            if subscribers is not None:
                return self._send_to_subscribers(subject, text_body, html_body, enabled, subscribers)
        html_body = with_unsubscribe_link(html_body, None)
        if recipients is not None:
            to_list, cc_list = list(recipients), []
        else:
            to_list, cc_list = self.settings.email_to_list, self.settings.email_cc_list
        recipients = [*to_list, *cc_list]
        recipients_text = ",".join(recipients)

        if not enabled:
            logger.info("Email delivery disabled", extra={"subject": subject})
            self._record(subject, recipients_text, "disabled")
            return False

        if self.settings.dry_run:
            logger.info("Email dry run; message not sent", extra={"subject": subject})
            self._record(subject, recipients_text, "dry_run")
            return False

        missing = self._missing_required_fields(recipients)
        if missing:
            error = f"Missing email configuration: {', '.join(missing)}"
            logger.error("Email configuration incomplete", extra={"missing": missing})
            self._record(subject, recipients_text, "error", error)
            return False

        message = self._build_message(subject, text_body, html_body, to_list, cc_list)

        try:
            with self._smtp() as smtp:
                smtp.send_message(message)
            logger.info("Email sent successfully", extra={"subject": subject, "recipients": len(recipients)})
            self._record(subject, recipients_text, "sent")
            return True
        except Exception as exc:
            logger.error("Failed to send email", extra={"subject": subject}, exc_info=True)
            self._record(subject, recipients_text, "error", str(exc))
            return False

    def _send_to_subscribers(self, subject, text_body, html_body, enabled, subscribers) -> bool:
        """Un correo por suscriptor activo: link de baja personal y RFC 8058."""
        total = len(subscribers)
        summary = f"{total} suscriptores activos"
        if not enabled:
            logger.info("Email delivery disabled", extra={"subject": subject, "subscribers": total})
            self._record(subject, summary, "disabled")
            return False
        if self.settings.dry_run:
            logger.info("Email dry run; message not sent", extra={"subject": subject, "subscribers": total})
            self._record(subject, summary, "dry_run")
            return False
        if not subscribers:
            logger.warning("No active subscribers; email not sent", extra={"subject": subject})
            self._record(subject, summary, "skipped", "Sin suscriptores activos")
            return False
        missing = self._missing_required_fields([subscriber.email for subscriber in subscribers])
        if missing:
            error = f"Missing email configuration: {', '.join(missing)}"
            logger.error("Email configuration incomplete", extra={"missing": missing})
            self._record(subject, summary, "error", error)
            return False

        sent = 0
        smtp = None
        try:
            for subscriber in subscribers:
                url = self.unsubscribe_url(subscriber.token)
                message = self._build_message(
                    subject,
                    text_with_unsubscribe_link(text_body, url),
                    with_unsubscribe_link(html_body, url),
                    [subscriber.email],
                    [],
                )
                # RFC 8058: Gmail y Outlook muestran "Cancelar suscripcion" y
                # hacen un POST a la URL, sin abrir la pagina.
                message["List-Unsubscribe"] = f"<{url}>"
                message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
                try:
                    if smtp is None:
                        smtp = self._smtp()
                    try:
                        smtp.send_message(message)
                    except smtplib.SMTPServerDisconnected:
                        smtp = self._smtp()
                        smtp.send_message(message)
                    sent += 1
                    self._record(subject, subscriber.email, "sent")
                except Exception as exc:
                    logger.error("Failed to send email to subscriber", extra={"subject": subject,
                                 "subscriber_id": subscriber.id}, exc_info=True)
                    self._record(subject, subscriber.email, "error", str(exc))
                    if isinstance(exc, smtplib.SMTPAuthenticationError | smtplib.SMTPServerDisconnected):
                        smtp = None
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except Exception:
                    pass
        logger.info("Email sent to subscribers", extra={"subject": subject, "sent": sent, "subscribers": total})
        return sent > 0

    def _load_subscribers(self):
        """Suscriptores activos, o None si falta configuracion o MySQL falla."""
        if not self.settings.mailing_public_url:
            logger.error("MAILING_ENABLED sin MAILING_PUBLIC_URL; se envia a EMAIL_TO")
            return None
        try:
            if self._subscribers is None:
                from storage.subscribers import SubscriberRepository

                self._subscribers = SubscriberRepository.from_settings(self.settings)
            return self._subscribers.active()
        except Exception as exc:
            logger.error("No se pudo leer la lista de suscriptores; se envia a EMAIL_TO",
                         extra={"error": type(exc).__name__})
            return None

    def unsubscribe_url(self, token: str) -> str:
        return f"{self.settings.mailing_public_url.rstrip('/')}/baja?t={token}"

    def _build_message(self, subject, text_body, html_body, to_list, cc_list) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_header()
        message["To"] = ", ".join(to_list)
        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")
        self._embed_logo(message, html_body)
        return message

    def _smtp(self) -> smtplib.SMTP:
        """Conexion SMTP autenticada, para usar como context manager."""
        smtp = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30)
        try:
            smtp.starttls()
            smtp.login(self.settings.smtp_user, self.settings.smtp_password)
        except Exception:
            smtp.close()
            raise
        return smtp

    def _from_header(self) -> str:
        address = self.settings.email_from
        if "<" in address or not self.settings.email_from_name:
            return address
        return formataddr((self.settings.email_from_name, address))

    def _embed_logo(self, message: EmailMessage, html_body: str) -> None:
        """Adjunta el logo como parte relacionada del HTML si este lo usa.

        Estructura: multipart/alternative -> [text/plain, multipart/related ->
        [text/html, image/png]]. Es la que Outlook (web, nuevo, movil), Gmail
        y Apple Mail muestran sin bloquear ni listar como adjunto.
        """
        if f"cid:{LOGO_CID}" not in html_body:
            return
        path = Path(self.settings.email_logo_embed_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        try:
            data = path.read_bytes()
        except OSError:
            logger.warning("Logo para embeber no encontrado; el correo mostrara el texto alternativo",
                           extra={"path": str(path)})
            return
        html_part = message.get_payload()[1]
        html_part.add_related(data, maintype="image", subtype="png", cid=f"<{LOGO_CID}>",
                              filename="dmac-logo.png", disposition="inline")

    def _missing_required_fields(self, recipients: list[str]) -> list[str]:
        missing = []
        if not self.settings.smtp_host:
            missing.append("SMTP_HOST")
        if not self.settings.smtp_user:
            missing.append("SMTP_USER")
        if not self.settings.smtp_password:
            missing.append("SMTP_PASSWORD")
        if not self.settings.email_from:
            missing.append("EMAIL_FROM")
        if not recipients:
            missing.append("EMAIL_TO")
        return missing

    def _record(self, subject: str, recipients: str, status: str, error_message: str = "") -> None:
        self.repository.save(
            SentEmail(
                timestamp=datetime.now(UTC),
                subject=subject,
                recipients=recipients,
                status=status,
                error_message=error_message,
            )
        )

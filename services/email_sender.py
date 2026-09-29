import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from app.config import Settings, get_settings
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
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or SentEmailRepository()

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
        """
        del inline_images  # deprecated: HTML is self-contained now
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

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_header()
        message["To"] = ", ".join(to_list)
        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")
        self._embed_logo(message, html_body)

        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(self.settings.smtp_user, self.settings.smtp_password)
                smtp.send_message(message)
            logger.info("Email sent successfully", extra={"subject": subject, "recipients": len(recipients)})
            self._record(subject, recipients_text, "sent")
            return True
        except Exception as exc:
            logger.error("Failed to send email", extra={"subject": subject}, exc_info=True)
            self._record(subject, recipients_text, "error", str(exc))
            return False

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

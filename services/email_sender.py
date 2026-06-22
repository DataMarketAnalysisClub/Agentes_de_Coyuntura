import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

from app.config import Settings, get_settings
from storage.models import SentEmail
from storage.repositories import SentEmailRepository

logger = logging.getLogger(__name__)


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
    ) -> bool:
        """Send the email via SMTP.

        `inline_images` is accepted for backward compatibility but ignored: the
        HTML body must contain its images as inline base64 data URIs (handled
        by the email_formatter). This avoids the cid: multipart/related
        issues that break image rendering in Outlook mobile and Outlook web.
        """
        del inline_images  # deprecated: HTML is self-contained now
        to_list = self.settings.email_to_list
        cc_list = self.settings.email_cc_list
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
        message["From"] = self.settings.email_from
        message["To"] = ", ".join(to_list)
        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

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

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from config import Settings


@dataclass
class EmailPayload:
    recipients: list[str]
    subject: str
    body: str
    attachment_path: Path


@dataclass
class EmailResult:
    enabled: bool
    dry_run: bool
    sent: bool
    recipients: list[str]
    subject: str
    message: str


class EmailManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _recipients_by_type(self, report_type: str) -> list[str]:
        normalized = report_type.lower().strip()
        if normalized == "weekly":
            return self.settings.email_recipients_weekly
        if normalized == "monthly":
            return self.settings.email_recipients_monthly
        if normalized == "annual":
            return self.settings.email_recipients_annual
        raise ValueError(f"Tipo de informe no soportado para email: {report_type}")

    def _subject_by_type(self, report_type: str) -> str:
        normalized = report_type.lower().strip()
        if normalized == "weekly":
            return self.settings.email_subject_weekly
        if normalized == "monthly":
            return self.settings.email_subject_monthly
        if normalized == "annual":
            return self.settings.email_subject_annual
        raise ValueError(f"Tipo de informe no soportado para email: {report_type}")

    def build_payload(
        self,
        report_type: str,
        period_label: str,
        attachment_path: Path,
    ) -> EmailPayload:
        recipients = self._recipients_by_type(report_type)
        subject = self._subject_by_type(report_type)
        body = (
            f"Hola,\n\n"
            f"Adjuntamos el informe {report_type} de {self.settings.company_name}.\n"
            f"Periodo analizado: {period_label}.\n"
            f"Desarrollado por: {self.settings.developer_name}.\n\n"
            "Este mensaje forma parte del flujo automatizado de reporting.\n"
        )

        return EmailPayload(
            recipients=recipients,
            subject=subject,
            body=body,
            attachment_path=attachment_path,
        )

    def send(self, payload: EmailPayload, dry_run: bool = True) -> EmailResult:
        if dry_run:
            return EmailResult(
                enabled=self.settings.email_enabled,
                dry_run=True,
                sent=False,
                recipients=payload.recipients,
                subject=payload.subject,
                message="Dry-run activo: email no enviado.",
            )

        if not self.settings.email_enabled:
            return EmailResult(
                enabled=False,
                dry_run=False,
                sent=False,
                recipients=payload.recipients,
                subject=payload.subject,
                message="EMAIL_ENABLED=False. Sistema preparado, envio desactivado.",
            )

        if not payload.recipients:
            return EmailResult(
                enabled=True,
                dry_run=False,
                sent=False,
                recipients=[],
                subject=payload.subject,
                message="No hay destinatarios configurados para este tipo de informe.",
            )

        message = EmailMessage()
        message["From"] = self.settings.email_sender
        message["To"] = ", ".join(payload.recipients)
        message["Subject"] = payload.subject
        message.set_content(payload.body)

        attachment_data = payload.attachment_path.read_bytes()
        message.add_attachment(
            attachment_data,
            maintype="application",
            subtype="pdf",
            filename=payload.attachment_path.name,
        )

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as smtp:
            smtp.starttls()
            if self.settings.smtp_username and self.settings.smtp_password:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)

        return EmailResult(
            enabled=True,
            dry_run=False,
            sent=True,
            recipients=payload.recipients,
            subject=payload.subject,
            message="Email enviado correctamente.",
        )

from pathlib import Path

from config import load_settings
from reporting.email_manager import EmailManager



def _build_settings():
    settings = load_settings()
    settings.email_enabled = False
    settings.email_recipients_weekly = ["direccion1@example.com", "direccion2@example.com"]
    settings.email_subject_weekly = "[Artes Buho] Informe Semanal"
    return settings



def test_email_dry_run_does_not_send():
    settings = _build_settings()
    manager = EmailManager(settings)

    payload = manager.build_payload(
        report_type="weekly",
        period_label="Semana 2026-03-30 a 2026-04-05",
        attachment_path=Path("/tmp/demo.pdf"),
    )

    result = manager.send(payload, dry_run=True)

    assert result.sent is False
    assert result.dry_run is True
    assert "Dry-run" in result.message



def test_email_disabled_even_without_dry_run():
    settings = _build_settings()
    manager = EmailManager(settings)

    payload = manager.build_payload(
        report_type="weekly",
        period_label="Semana 2026-03-30 a 2026-04-05",
        attachment_path=Path("/tmp/demo.pdf"),
    )

    result = manager.send(payload, dry_run=False)

    assert result.sent is False
    assert result.enabled is False
    assert "EMAIL_ENABLED=False" in result.message

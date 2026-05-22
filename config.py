from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

DEFAULT_SPREADSHEET_ID = "REPLACE_WITH_SHEET_ID"
DEFAULT_PANEL_NAME = "PANEL BI ARTES BUHO"
DEFAULT_TIMEZONE = "Europe/Madrid"


@dataclass
class Settings:
    project_root: Path
    spreadsheet_id: str
    panel_name: str
    timezone: str

    company_name: str
    developer_name: str
    logo_path: Path

    public_gid_candidates: list[str]
    preferred_sheet_keywords: list[str]

    simulation_clients: int
    simulation_invoices: int
    simulation_lines: int
    simulation_articles: int
    simulation_seed: int

    service_account_file: Path | None
    oauth_token_file: Path | None

    streamlit_app_url: str | None
    drive_launcher_doc_name: str

    report_output_dir: Path
    drive_reports_root_name: str
    drive_weekly_folder_name: str
    drive_monthly_folder_name: str
    drive_annual_folder_name: str

    email_enabled: bool
    email_sender: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    email_recipients_weekly: list[str]
    email_recipients_monthly: list[str]
    email_recipients_annual: list[str]
    email_subject_weekly: str
    email_subject_monthly: str
    email_subject_annual: str



def _split_csv(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]



def _to_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default



def _to_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "t", "yes", "y", "si", "s"}



def _resolve_optional_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    return Path(text).expanduser()



def _resolve_path(raw: str, project_root: Path) -> Path:
    text = raw.strip()
    path = Path(text)
    if not path.is_absolute():
        path = project_root / path
    return path



def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent
    env_file = project_root / ".env"
    if load_dotenv and env_file.exists():
        load_dotenv(env_file)

    spreadsheet_id = os.getenv("SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID).strip()
    panel_name = os.getenv("PANEL_NAME", DEFAULT_PANEL_NAME).strip()
    timezone = os.getenv("TIMEZONE", DEFAULT_TIMEZONE).strip()

    company_name = os.getenv("COMPANY_NAME", "ARTES BUHO").strip()
    developer_name = os.getenv("DEVELOPER_NAME", "RUBEN COTON").strip()

    logo_path = _resolve_path(os.getenv("LOGO_PATH", "assets/logo_artes_buho.png"), project_root)

    public_gid_candidates = _split_csv(os.getenv("PUBLIC_GID_CANDIDATES", "0"))
    preferred_sheet_keywords = _split_csv(
        os.getenv(
            "PREFERRED_SHEET_KEYWORDS",
            "facturas,ventas,data,datos,principal,resumen,orders",
        )
    )

    simulation_clients = _to_int("SIM_CLIENTES", 100)
    simulation_invoices = _to_int("SIM_FACTURAS", 500)
    simulation_lines = _to_int("SIM_LINEAS", 2000)
    simulation_articles = _to_int("SIM_ARTICULOS", 120)
    simulation_seed = _to_int("SIM_SEED", 42)

    service_account_file = _resolve_optional_path(os.getenv("GOOGLE_CREDENTIALS_FILE"))
    oauth_token_file = _resolve_optional_path(
        os.getenv("GOOGLE_OAUTH_TOKEN_FILE") or os.getenv("GOOGLE_TOKEN_FILE")
    )

    streamlit_app_url = os.getenv("STREAMLIT_APP_URL", "").strip() or None
    drive_launcher_doc_name = os.getenv(
        "DRIVE_LAUNCHER_DOC_NAME",
        f"ABRIR PANEL - {panel_name}",
    ).strip()

    report_output_dir = _resolve_path(os.getenv("REPORT_OUTPUT_DIR", "generated_reports"), project_root)
    drive_reports_root_name = os.getenv("DRIVE_REPORTS_ROOT_NAME", "Informes").strip()
    drive_weekly_folder_name = os.getenv("DRIVE_REPORT_WEEKLY_FOLDER", "InformeSemanal").strip()
    drive_monthly_folder_name = os.getenv("DRIVE_REPORT_MONTHLY_FOLDER", "InformeMensual").strip()
    drive_annual_folder_name = os.getenv("DRIVE_REPORT_ANNUAL_FOLDER", "InformeAnual").strip()

    email_enabled = _to_bool("EMAIL_ENABLED", False)
    email_sender = os.getenv("EMAIL_SENDER", "reportes@artesbuho.local").strip()
    smtp_host = os.getenv("SMTP_HOST", "smtp.example.com").strip()
    smtp_port = _to_int("SMTP_PORT", 587)
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()

    email_recipients_weekly = _split_csv(os.getenv("EMAIL_RECIPIENTS_WEEKLY", ""))
    email_recipients_monthly = _split_csv(os.getenv("EMAIL_RECIPIENTS_MONTHLY", ""))
    email_recipients_annual = _split_csv(os.getenv("EMAIL_RECIPIENTS_ANNUAL", ""))

    email_subject_weekly = os.getenv(
        "EMAIL_SUBJECT_WEEKLY",
        "[Artes Buho] Informe Semanal",
    ).strip()
    email_subject_monthly = os.getenv(
        "EMAIL_SUBJECT_MONTHLY",
        "[Artes Buho] Informe Mensual",
    ).strip()
    email_subject_annual = os.getenv(
        "EMAIL_SUBJECT_ANNUAL",
        "[Artes Buho] Informe Anual",
    ).strip()

    if not spreadsheet_id:
        raise ValueError("SPREADSHEET_ID no puede estar vacio.")

    return Settings(
        project_root=project_root,
        spreadsheet_id=spreadsheet_id,
        panel_name=panel_name,
        timezone=timezone,
        company_name=company_name,
        developer_name=developer_name,
        logo_path=logo_path,
        public_gid_candidates=public_gid_candidates,
        preferred_sheet_keywords=preferred_sheet_keywords,
        simulation_clients=simulation_clients,
        simulation_invoices=simulation_invoices,
        simulation_lines=simulation_lines,
        simulation_articles=simulation_articles,
        simulation_seed=simulation_seed,
        service_account_file=service_account_file,
        oauth_token_file=oauth_token_file,
        streamlit_app_url=streamlit_app_url,
        drive_launcher_doc_name=drive_launcher_doc_name,
        report_output_dir=report_output_dir,
        drive_reports_root_name=drive_reports_root_name,
        drive_weekly_folder_name=drive_weekly_folder_name,
        drive_monthly_folder_name=drive_monthly_folder_name,
        drive_annual_folder_name=drive_annual_folder_name,
        email_enabled=email_enabled,
        email_sender=email_sender,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        email_recipients_weekly=email_recipients_weekly,
        email_recipients_monthly=email_recipients_monthly,
        email_recipients_annual=email_recipients_annual,
        email_subject_weekly=email_subject_weekly,
        email_subject_monthly=email_subject_monthly,
        email_subject_annual=email_subject_annual,
    )

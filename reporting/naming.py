from __future__ import annotations

from datetime import datetime

from reporting.periods import ReportPeriod



def build_report_filename(report_type: str, run_datetime: datetime, period: ReportPeriod) -> str:
    normalized = report_type.lower().strip()

    if normalized == "weekly":
        return f"{run_datetime.strftime('%y%m%d')}_InformeSemanal.pdf"

    if normalized == "monthly":
        return f"{period.start_date.strftime('%y%m')}_InformeMensual.pdf"

    if normalized == "annual":
        return f"{period.start_date.strftime('%Y')}_InformeAnual.pdf"

    raise ValueError(f"Tipo de informe no soportado: {report_type}")

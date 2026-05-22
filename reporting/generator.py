from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from config import Settings, load_settings
from reporting.drive_manager import DriveReportManager, ReportFolderStructure, UploadResult
from reporting.email_manager import EmailManager, EmailResult
from reporting.naming import build_report_filename
from reporting.periods import (
    ReportPeriod,
    calculate_previous_period,
    calculate_report_period,
    parse_run_datetime,
)
from shared.analytics import (
    KPIItem,
    build_category_ranking,
    build_kpis,
    build_time_series,
    select_detail_columns,
)
from shared.data_loader import get_sheet_frame, load_data_bundle
from shared.insights import generate_insights, pick_date_col


@dataclass
class ReportGenerationResult:
    report_type: str
    run_datetime: str
    period_start: str
    period_end: str
    file_name: str
    local_pdf_path: str
    sheet_used: str
    records_current_period: int
    records_previous_period: int
    drive_status: dict
    email_status: dict

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class ReportGenerator:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self._pdf_builder = None
        self.email_manager = EmailManager(self.settings)

    def _pdf(self):
        if self._pdf_builder is None:
            from reporting.pdf_builder import PdfReportBuilder

            self._pdf_builder = PdfReportBuilder()
        return self._pdf_builder

    @staticmethod
    def _filter_period(frame: pd.DataFrame, date_col: str, period: ReportPeriod) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()

        source = frame.copy()
        dates = pd.to_datetime(source[date_col], errors="coerce")
        start_date = period.start_date
        end_date = period.end_date

        mask = (dates.dt.date >= start_date) & (dates.dt.date <= end_date)
        filtered = source.loc[mask].copy()
        return filtered

    @staticmethod
    def _summary_from_kpis(
        report_type: str,
        period: ReportPeriod,
        kpis: list[KPIItem],
        insights: list[str],
    ) -> list[str]:
        lines: list[str] = []

        if report_type == "weekly":
            lines.append(
                f"Informe operativo semanal para el periodo {period.start_date} a {period.end_date}."
            )
        elif report_type == "monthly":
            lines.append(
                f"Informe ejecutivo mensual del periodo {period.start_date:%Y-%m}."
            )
        else:
            lines.append(
                f"Informe estratégico anual del periodo {period.start_date:%Y}."
            )

        for kpi in kpis[:3]:
            if kpi.delta_pct is None:
                lines.append(f"{kpi.name}: {kpi.value:.2f}.")
            else:
                trend = "sube" if kpi.delta_pct >= 0 else "baja"
                lines.append(f"{kpi.name}: {kpi.value:.2f} ({trend} {abs(kpi.delta_pct):.1f}% vs periodo previo).")

        if insights:
            lines.append(f"Insight destacado: {insights[0]}")

        return lines

    @staticmethod
    def _methodology_note(sheet_name: str, source_method: str) -> str:
        return (
            "Extracción y normalización automática desde Google Sheets. "
            f"Pestaña analizada: {sheet_name}. "
            f"Método de carga: {source_method}. "
            "La capa analítica compartida reutiliza reglas de tipado, métricas e insights del dashboard."
        )

    def _build_pdf_data(
        self,
        report_type: str,
        period: ReportPeriod,
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        semantics: dict[str, str],
        sheet_name: str,
        source_method: str,
    ):
        from reporting.pdf_builder import PdfReportData

        kpis = build_kpis(current_df, previous_df, semantics)
        time_series = build_time_series(current_df, semantics)
        category_ranking = build_category_ranking(current_df, semantics)
        insights = generate_insights(current_df, semantics)
        detail_cols = select_detail_columns(current_df, semantics, limit=8)
        detail_df = current_df[detail_cols].copy() if detail_cols else current_df.copy()

        summary = self._summary_from_kpis(report_type, period, kpis, insights)

        return PdfReportData(
            executive_summary=summary,
            kpis=kpis,
            time_series=time_series,
            category_ranking=category_ranking,
            detail_table=detail_df,
            insights=insights,
            methodology_note=self._methodology_note(sheet_name, source_method),
        )

    def _report_title(self, report_type: str) -> str:
        if report_type == "weekly":
            return "Informe Semanal"
        if report_type == "monthly":
            return "Informe Mensual"
        return "Informe Anual"

    def generate(
        self,
        report_type: str,
        run_datetime_text: str | None,
        dry_run: bool = False,
        overwrite: bool = False,
        upload_drive: bool = True,
        enable_email_send: bool = False,
        output_dir: Path | None = None,
    ) -> ReportGenerationResult:
        report_type = report_type.lower().strip()
        run_dt = parse_run_datetime(run_datetime_text, self.settings.timezone)

        period = calculate_report_period(report_type, run_dt, self.settings.timezone)
        previous_period = calculate_previous_period(period)

        bundle = load_data_bundle(self.settings)
        sheet_name, frame, semantics = get_sheet_frame(bundle, None)

        date_col = pick_date_col(frame, semantics)
        if not date_col:
            raise RuntimeError(
                "No se detectó columna de fecha en la hoja principal. "
                "El sistema de informes requiere dimensión temporal."
            )

        current_df = self._filter_period(frame, date_col, period)
        previous_df = self._filter_period(frame, date_col, previous_period)

        pdf_data = self._build_pdf_data(
            report_type=report_type,
            period=period,
            current_df=current_df,
            previous_df=previous_df,
            semantics=semantics,
            sheet_name=sheet_name,
            source_method=bundle.source_method,
        )

        report_title = self._report_title(report_type)
        file_name = build_report_filename(report_type, run_dt, period)

        base_output_dir = output_dir or self.settings.report_output_dir
        target_dir = base_output_dir / report_type
        local_pdf_path = target_dir / file_name

        from reporting.pdf_builder import PdfReportContext

        context = PdfReportContext(
            report_type=report_type,
            report_title=report_title,
            company_name=self.settings.company_name,
            developer_name=self.settings.developer_name,
            period_label=period.label,
            run_datetime=run_dt,
            timezone=self.settings.timezone,
            logo_path=self.settings.logo_path,
        )

        self._pdf().build(local_pdf_path, context, pdf_data)

        drive_status: dict
        if dry_run or not upload_drive:
            drive_status = {
                "uploaded": False,
                "skipped": True,
                "message": "Dry-run o upload desactivado: no se sube PDF a Drive.",
            }
        else:
            try:
                drive_manager = DriveReportManager(self.settings)
                structure: ReportFolderStructure = drive_manager.ensure_reports_structure(self.settings.spreadsheet_id)
                upload_result: UploadResult = drive_manager.upload_report(
                    report_type=report_type,
                    local_pdf_path=local_pdf_path,
                    folder_structure=structure,
                    overwrite=overwrite,
                )
                drive_status = asdict(upload_result)
                drive_status["folder_structure"] = asdict(structure)
            except Exception as exc:
                audit_dir = self.settings.project_root / "audit"
                audit_dir.mkdir(parents=True, exist_ok=True)
                fallback_file = audit_dir / "drive_upload_fallback.md"
                fallback_file.write_text(
                    (
                        "# Fallback subida de informes a Drive\n\n"
                        f"Motivo: {exc}\n\n"
                        "## Estructura requerida\n\n"
                        "Informes/\n"
                        "  InformeSemanal/\n"
                        "  InformeMensual/\n"
                        "  InformeAnual/\n\n"
                        f"## Archivo local generado\n\n{local_pdf_path}\n"
                    ),
                    encoding="utf-8",
                )
                drive_status = {
                    "uploaded": False,
                    "skipped": True,
                    "message": "No se pudo subir a Drive desde este entorno. Se dejó fallback documental.",
                    "error": str(exc),
                    "fallback_file": str(fallback_file),
                }

        payload = self.email_manager.build_payload(report_type, period.label, local_pdf_path)
        email_dry_run = True if not enable_email_send else dry_run
        email_result: EmailResult = self.email_manager.send(payload, dry_run=email_dry_run)

        return ReportGenerationResult(
            report_type=report_type,
            run_datetime=run_dt.isoformat(),
            period_start=period.start_date.isoformat(),
            period_end=period.end_date.isoformat(),
            file_name=file_name,
            local_pdf_path=str(local_pdf_path),
            sheet_used=sheet_name,
            records_current_period=int(len(current_df)),
            records_previous_period=int(len(previous_df)),
            drive_status=drive_status,
            email_status=asdict(email_result),
        )

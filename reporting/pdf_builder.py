from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from shared.analytics import KPIItem


@dataclass
class PdfReportContext:
    report_type: str
    report_title: str
    company_name: str
    developer_name: str
    period_label: str
    run_datetime: datetime
    timezone: str
    logo_path: Path


@dataclass
class PdfReportData:
    executive_summary: list[str]
    kpis: list[KPIItem]
    time_series: pd.DataFrame
    category_ranking: pd.DataFrame
    detail_table: pd.DataFrame
    insights: list[str]
    methodology_note: str


class PdfReportBuilder:
    RED = colors.HexColor("#FF0000")
    YELLOW = colors.HexColor("#FFD700")
    WHITE = colors.HexColor("#FFFFFF")
    DARK = colors.HexColor("#202020")

    def __init__(self) -> None:
        base_styles = getSampleStyleSheet()
        self.styles = {
            "title": ParagraphStyle(
                "title",
                parent=base_styles["Title"],
                fontName="Helvetica-Bold",
                fontSize=20,
                textColor=self.RED,
                spaceAfter=14,
            ),
            "subtitle": ParagraphStyle(
                "subtitle",
                parent=base_styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=13,
                textColor=self.DARK,
                spaceAfter=8,
            ),
            "normal": ParagraphStyle(
                "normal",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=10,
                textColor=self.DARK,
                leading=14,
            ),
            "small": ParagraphStyle(
                "small",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=8,
                textColor=self.DARK,
            ),
        }

    @staticmethod
    def _fmt_value(value: float | int | None, semantic: str | None) -> str:
        if value is None:
            return "n/d"
        if semantic == "porcentaje":
            return f"{float(value) * 100:.2f}%"
        if semantic == "importe_monetario":
            return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        if isinstance(value, (int, float)):
            return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return str(value)

    @staticmethod
    def _fmt_delta(delta: float | None) -> str:
        if delta is None:
            return "n/d"
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.1f}%"

    def _build_cover(self, context: PdfReportContext) -> list:
        items: list = []

        if context.logo_path.exists():
            logo = Image(str(context.logo_path), width=3.2 * cm, height=3.2 * cm)
            logo.hAlign = "LEFT"
            items.append(logo)
            items.append(Spacer(1, 0.35 * cm))

        items.append(Paragraph(context.company_name, self.styles["title"]))
        items.append(Paragraph(context.report_title, self.styles["subtitle"]))
        items.append(Paragraph(f"Periodo: {context.period_label}", self.styles["normal"]))
        items.append(
            Paragraph(
                f"Fecha de generacion: {context.run_datetime.strftime('%Y-%m-%d %H:%M')} ({context.timezone})",
                self.styles["normal"],
            )
        )
        items.append(Paragraph(f"Desarrollador del sistema: {context.developer_name}", self.styles["normal"]))
        items.append(Spacer(1, 0.6 * cm))
        return items

    def _build_summary(self, lines: list[str]) -> list:
        items: list = [Paragraph("Resumen ejecutivo", self.styles["subtitle"])]
        if not lines:
            lines = ["Sin observaciones relevantes para el periodo seleccionado."]
        for line in lines:
            items.append(Paragraph(f"• {line}", self.styles["normal"]))
        items.append(Spacer(1, 0.4 * cm))
        return items

    def _build_kpi_table(self, kpis: list[KPIItem]) -> list:
        items: list = [Paragraph("KPIs principales", self.styles["subtitle"])]
        rows = [["Indicador", "Valor", "Periodo previo", "Variacion"]]
        for kpi in kpis:
            rows.append(
                [
                    kpi.name,
                    self._fmt_value(kpi.value, kpi.semantic),
                    self._fmt_value(kpi.previous_value, kpi.semantic),
                    self._fmt_delta(kpi.delta_pct),
                ]
            )

        table = Table(rows, colWidths=[5.5 * cm, 3.5 * cm, 3.5 * cm, 3 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self.RED),
                    ("TEXTCOLOR", (0, 0), (-1, 0), self.WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, self.YELLOW]),
                ]
            )
        )
        items.append(table)
        items.append(Spacer(1, 0.4 * cm))
        return items

    def _save_line_chart(self, frame: pd.DataFrame) -> BytesIO | None:
        if frame.empty:
            return None
        fig, ax = plt.subplots(figsize=(8, 3.2), dpi=120)
        ax.plot(frame["periodo"], frame["valor"], color="#FF0000", linewidth=2)
        ax.set_title("Evolucion temporal")
        ax.set_xlabel("Periodo")
        ax.set_ylabel("Valor")
        ax.grid(alpha=0.2)
        fig.autofmt_xdate()
        fig.tight_layout()
        buffer = BytesIO()
        fig.savefig(buffer, format="png", facecolor="white")
        buffer.seek(0)
        plt.close(fig)
        return buffer

    def _save_bar_chart(self, frame: pd.DataFrame) -> BytesIO | None:
        if frame.empty:
            return None
        fig, ax = plt.subplots(figsize=(8, 3.2), dpi=120)
        ax.bar(frame["categoria"].astype(str), frame["valor"], color="#FFD700", edgecolor="#FF0000")
        ax.set_title("Ranking por categoria")
        ax.set_xlabel("Categoria")
        ax.set_ylabel("Valor")
        ax.tick_params(axis="x", rotation=35)
        fig.tight_layout()
        buffer = BytesIO()
        fig.savefig(buffer, format="png", facecolor="white")
        buffer.seek(0)
        plt.close(fig)
        return buffer

    def _build_charts(self, time_series: pd.DataFrame, ranking: pd.DataFrame) -> list:
        items: list = [Paragraph("Visualizaciones", self.styles["subtitle"])]
        line_buffer = self._save_line_chart(time_series)
        bar_buffer = self._save_bar_chart(ranking)

        if line_buffer is not None:
            chart = Image(line_buffer, width=16 * cm, height=6.4 * cm)
            chart.hAlign = "CENTER"
            items.append(chart)
            items.append(Spacer(1, 0.2 * cm))

        if bar_buffer is not None:
            chart = Image(bar_buffer, width=16 * cm, height=6.4 * cm)
            chart.hAlign = "CENTER"
            items.append(chart)
            items.append(Spacer(1, 0.4 * cm))

        return items

    def _build_detail_table(self, detail_df: pd.DataFrame) -> list:
        items: list = [Paragraph("Detalle de datos", self.styles["subtitle"])]
        if detail_df.empty:
            items.append(Paragraph("No hay detalle disponible para el periodo.", self.styles["normal"]))
            items.append(Spacer(1, 0.4 * cm))
            return items

        max_rows = min(15, len(detail_df))
        sample = detail_df.head(max_rows).copy()
        rows = [sample.columns.tolist()] + sample.astype(str).values.tolist()

        col_count = len(sample.columns)
        table = Table(rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self.RED),
                    ("TEXTCOLOR", (0, 0), (-1, 0), self.WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
                    ("ALIGN", (0, 0), (col_count - 1, 0), "CENTER"),
                ]
            )
        )

        items.append(table)
        items.append(Spacer(1, 0.4 * cm))
        return items

    def _build_insights(self, insights: list[str]) -> list:
        items: list = [Paragraph("Insights automaticos", self.styles["subtitle"])]
        if not insights:
            insights = ["No hay insights concluyentes para este periodo."]
        for line in insights:
            items.append(Paragraph(f"• {line}", self.styles["normal"]))
        items.append(Spacer(1, 0.35 * cm))
        return items

    def _build_methodology(self, note: str) -> list:
        return [
            Paragraph("Nota metodologica", self.styles["subtitle"]),
            Paragraph(note, self.styles["small"]),
        ]

    def _on_page(self, canvas, doc):
        page_number = canvas.getPageNumber()
        canvas.setStrokeColor(self.RED)
        canvas.setLineWidth(1)
        canvas.line(1.5 * cm, 1.5 * cm, A4[0] - 1.5 * cm, 1.5 * cm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(self.DARK)
        canvas.drawString(1.7 * cm, 1.0 * cm, "Artes Buho - Sistema de Informes Corporativos")
        canvas.drawRightString(A4[0] - 1.7 * cm, 1.0 * cm, f"Pagina {page_number}")

    def build(self, output_pdf_path: Path, context: PdfReportContext, data: PdfReportData) -> Path:
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

        elements: list = []
        elements.extend(self._build_cover(context))
        elements.extend(self._build_summary(data.executive_summary))
        elements.extend(self._build_kpi_table(data.kpis))

        charts = self._build_charts(data.time_series, data.category_ranking)
        elements.extend(charts)

        elements.extend(self._build_detail_table(data.detail_table))
        elements.extend(self._build_insights(data.insights))
        elements.extend(self._build_methodology(data.methodology_note))

        document = SimpleDocTemplate(
            str(output_pdf_path),
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.8 * cm,
            title=context.report_title,
            author=context.developer_name,
        )

        document.build(elements, onFirstPage=self._on_page, onLaterPages=self._on_page)
        return output_pdf_path

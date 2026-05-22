from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


REPORT_TYPES = {"weekly", "monthly", "annual"}


@dataclass(frozen=True)
class ReportPeriod:
    report_type: str
    start_date: date
    end_date: date
    run_datetime: datetime
    timezone: str

    @property
    def label(self) -> str:
        if self.report_type == "weekly":
            return f"Semana del {self.start_date.isoformat()} al {self.end_date.isoformat()}"
        if self.report_type == "monthly":
            return f"Mes {self.start_date.strftime('%Y-%m')}"
        return f"Año {self.start_date.strftime('%Y')}"

    def to_datetime_range(self) -> tuple[datetime, datetime]:
        tz = ZoneInfo(self.timezone)
        start_dt = datetime.combine(self.start_date, time(0, 0, 0), tzinfo=tz)
        end_dt = datetime.combine(self.end_date, time(23, 59, 59), tzinfo=tz)
        return start_dt, end_dt



def parse_run_datetime(value: str | None, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    if not value:
        return datetime.now(tz)

    text = value.strip()
    dt: datetime
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)

    return dt



def calculate_weekly_period(run_datetime: datetime, timezone: str) -> ReportPeriod:
    run_local = run_datetime.astimezone(ZoneInfo(timezone))
    current_week_monday = run_local.date() - timedelta(days=run_local.weekday())
    start_date = current_week_monday - timedelta(days=7)
    end_date = current_week_monday - timedelta(days=1)
    return ReportPeriod(
        report_type="weekly",
        start_date=start_date,
        end_date=end_date,
        run_datetime=run_local,
        timezone=timezone,
    )



def calculate_monthly_period(run_datetime: datetime, timezone: str) -> ReportPeriod:
    run_local = run_datetime.astimezone(ZoneInfo(timezone))
    first_day_current_month = run_local.date().replace(day=1)
    end_date = first_day_current_month - timedelta(days=1)
    start_date = end_date.replace(day=1)
    return ReportPeriod(
        report_type="monthly",
        start_date=start_date,
        end_date=end_date,
        run_datetime=run_local,
        timezone=timezone,
    )



def calculate_annual_period(run_datetime: datetime, timezone: str) -> ReportPeriod:
    run_local = run_datetime.astimezone(ZoneInfo(timezone))
    previous_year = run_local.year - 1
    start_date = date(previous_year, 1, 1)
    end_date = date(previous_year, 12, 31)
    return ReportPeriod(
        report_type="annual",
        start_date=start_date,
        end_date=end_date,
        run_datetime=run_local,
        timezone=timezone,
    )



def calculate_report_period(report_type: str, run_datetime: datetime, timezone: str) -> ReportPeriod:
    normalized = report_type.lower().strip()
    if normalized not in REPORT_TYPES:
        raise ValueError(f"Tipo de informe no soportado: {report_type}")

    if normalized == "weekly":
        return calculate_weekly_period(run_datetime, timezone)
    if normalized == "monthly":
        return calculate_monthly_period(run_datetime, timezone)
    return calculate_annual_period(run_datetime, timezone)



def calculate_previous_period(current_period: ReportPeriod) -> ReportPeriod:
    if current_period.report_type == "weekly":
        prev_start = current_period.start_date - timedelta(days=7)
        prev_end = current_period.end_date - timedelta(days=7)
    elif current_period.report_type == "monthly":
        prev_end = current_period.start_date - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
    else:
        prev_year = current_period.start_date.year - 1
        prev_start = date(prev_year, 1, 1)
        prev_end = date(prev_year, 12, 31)

    return ReportPeriod(
        report_type=current_period.report_type,
        start_date=prev_start,
        end_date=prev_end,
        run_datetime=current_period.run_datetime,
        timezone=current_period.timezone,
    )

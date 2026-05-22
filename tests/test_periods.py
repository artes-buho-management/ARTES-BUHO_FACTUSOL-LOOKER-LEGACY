from datetime import date

from reporting.periods import (
    calculate_annual_period,
    calculate_monthly_period,
    calculate_weekly_period,
    parse_run_datetime,
)



def test_weekly_period_example():
    run_dt = parse_run_datetime("2026-04-06 08:00", "Europe/Madrid")
    period = calculate_weekly_period(run_dt, "Europe/Madrid")

    assert period.start_date == date(2026, 3, 30)
    assert period.end_date == date(2026, 4, 5)



def test_monthly_period_example():
    run_dt = parse_run_datetime("2026-04-01 08:00", "Europe/Madrid")
    period = calculate_monthly_period(run_dt, "Europe/Madrid")

    assert period.start_date == date(2026, 3, 1)
    assert period.end_date == date(2026, 3, 31)



def test_annual_period_example():
    run_dt = parse_run_datetime("2027-01-01 08:00", "Europe/Madrid")
    period = calculate_annual_period(run_dt, "Europe/Madrid")

    assert period.start_date == date(2026, 1, 1)
    assert period.end_date == date(2026, 12, 31)

from reporting.naming import build_report_filename
from reporting.periods import calculate_report_period, parse_run_datetime



def test_weekly_filename_example():
    run_dt = parse_run_datetime("2026-04-06 08:00", "Europe/Madrid")
    period = calculate_report_period("weekly", run_dt, "Europe/Madrid")
    name = build_report_filename("weekly", run_dt, period)
    assert name == "260406_InformeSemanal.pdf"



def test_monthly_filename_example():
    run_dt = parse_run_datetime("2026-04-01 08:00", "Europe/Madrid")
    period = calculate_report_period("monthly", run_dt, "Europe/Madrid")
    name = build_report_filename("monthly", run_dt, period)
    assert name == "2603_InformeMensual.pdf"



def test_annual_filename_example():
    run_dt = parse_run_datetime("2027-01-01 08:00", "Europe/Madrid")
    period = calculate_report_period("annual", run_dt, "Europe/Madrid")
    name = build_report_filename("annual", run_dt, period)
    assert name == "2026_InformeAnual.pdf"

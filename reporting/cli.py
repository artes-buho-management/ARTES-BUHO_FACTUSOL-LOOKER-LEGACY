from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import load_settings
from reporting.periods import calculate_report_period, parse_run_datetime



def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting-cli",
        description="Sistema de informes corporativos Artes Buho.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generar informe PDF")
    generate.add_argument("report_type", choices=["weekly", "monthly", "annual"], help="Tipo de informe")
    generate.add_argument("--run-datetime", dest="run_datetime", default=None, help="Formato YYYY-MM-DD HH:MM o ISO")
    generate.add_argument("--dry-run", action="store_true", help="Genera PDF y preview sin subir a Drive")
    generate.add_argument("--overwrite", action="store_true", help="Sobrescribe PDF existente en Drive")
    generate.add_argument("--skip-drive-upload", action="store_true", help="No subir a Drive")
    generate.add_argument("--output-dir", default=None, help="Ruta local de salida para PDFs")

    prepare = subparsers.add_parser("prepare-drive", help="Crear/reutilizar estructura de carpetas en Drive")
    prepare.add_argument("--spreadsheet-id", default=None, help="ID de hoja fuente. Por defecto .env")

    preview = subparsers.add_parser("preview-email", help="Vista previa de email (sin envio)")
    preview.add_argument("report_type", choices=["weekly", "monthly", "annual"], help="Tipo de informe")
    preview.add_argument("--run-datetime", dest="run_datetime", default=None, help="Formato YYYY-MM-DD HH:MM o ISO")

    return parser



def _cmd_generate(args: argparse.Namespace) -> int:
    from reporting.generator import ReportGenerator

    generator = ReportGenerator(load_settings())
    output_dir = Path(args.output_dir) if args.output_dir else None

    result = generator.generate(
        report_type=args.report_type,
        run_datetime_text=args.run_datetime,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        upload_drive=not args.skip_drive_upload,
        enable_email_send=False,
        output_dir=output_dir,
    )
    print(result.to_json())
    return 0



def _cmd_prepare_drive(args: argparse.Namespace) -> int:
    from reporting.drive_manager import DriveReportManager

    settings = load_settings()
    manager = DriveReportManager(settings)
    try:
        structure = manager.ensure_reports_structure(args.spreadsheet_id)
        print(json.dumps(structure.__dict__, ensure_ascii=False, indent=2))
    except Exception as exc:
        audit_dir = settings.project_root / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        fallback_file = audit_dir / "drive_reports_structure_fallback.md"
        fallback_file.write_text(
            (
                "# Fallback estructura Drive para informes\n\n"
                f"Motivo: {exc}\n\n"
                "## Estructura obligatoria\n\n"
                "Informes/\n"
                "  InformeSemanal/\n"
                "  InformeMensual/\n"
                "  InformeAnual/\n\n"
                "## Comando preparado\n\n"
                "```powershell\n"
                "python main.py prepare-drive\n"
                "```\n\n"
                "## Nota\n\n"
                "Cuando la API devuelva carpeta padre de la hoja fuente, el comando la creara/reutilizara automaticamente.\n"
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": "fallback",
                    "error": str(exc),
                    "fallback_file": str(fallback_file),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0



def _cmd_preview_email(args: argparse.Namespace) -> int:
    from reporting.email_manager import EmailManager

    settings = load_settings()
    run_dt = parse_run_datetime(args.run_datetime, settings.timezone)
    period = calculate_report_period(args.report_type, run_dt, settings.timezone)

    email_manager = EmailManager(settings)
    fake_file = settings.report_output_dir / args.report_type / "demo.pdf"
    payload = email_manager.build_payload(args.report_type, period.label, fake_file)
    result = email_manager.send(payload, dry_run=True)

    print(
        json.dumps(
            {
                "report_type": args.report_type,
                "period": period.label,
                "payload": {
                    "recipients": payload.recipients,
                    "subject": payload.subject,
                    "body": payload.body,
                    "attachment_path": str(payload.attachment_path),
                },
                "email_result": result.__dict__,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0



def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "generate":
        return _cmd_generate(args)
    if args.command == "prepare-drive":
        return _cmd_prepare_drive(args)
    if args.command == "preview-email":
        return _cmd_preview_email(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

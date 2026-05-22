from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build


def _load_runtime_dependencies():
    import sys

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from config import load_settings
    from data_processing import DOCS_RW_SCOPES, DRIVE_RW_SCOPES, get_google_credentials

    return load_settings, DOCS_RW_SCOPES, DRIVE_RW_SCOPES, get_google_credentials


def _escape_query_value(value: str) -> str:
    return value.replace("'", "\\'")


def _build_doc_text(panel_name: str, panel_url: str, timezone: str) -> str:
    now_local = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"ABRIR PANEL - {panel_name}\n\n"
        "Documento lanzador de acceso al panel analitico.\n\n"
        f"URL del panel: {panel_url}\n\n"
        "Uso rapido:\n"
        "1. Haz clic en la URL del panel.\n"
        "2. Aplica filtros por fecha o categoria.\n"
        "3. Revisa KPIs, insights y detalle de registros.\n"
        "4. Comparte esta misma URL con el equipo autorizado.\n\n"
        f"Ultima actualizacion del lanzador: {now_local} ({timezone})\n"
    )


def _find_or_create_doc(drive_service, docs_service, parent_folder_id: str, doc_name: str) -> tuple[str, str]:
    escaped_name = _escape_query_value(doc_name)
    query = (
        f"'{parent_folder_id}' in parents and trashed=false "
        f"and mimeType='application/vnd.google-apps.document' and name='{escaped_name}'"
    )

    response = drive_service.files().list(
        q=query,
        spaces="drive",
        fields="files(id,name,webViewLink)",
        pageSize=1,
    ).execute()

    files = response.get("files", [])
    if files:
        file_info = files[0]
        return file_info["id"], file_info.get("webViewLink", "")

    doc = docs_service.documents().create(body={"title": doc_name}).execute()
    document_id = doc["documentId"]

    current_parents = (
        drive_service.files()
        .get(fileId=document_id, fields="parents")
        .execute()
        .get("parents", [])
    )
    remove_parents = ",".join(current_parents) if current_parents else None

    updated = (
        drive_service.files()
        .update(
            fileId=document_id,
            addParents=parent_folder_id,
            removeParents=remove_parents,
            fields="id,webViewLink",
        )
        .execute()
    )

    return updated["id"], updated.get("webViewLink", "")


def _replace_document_content(docs_service, document_id: str, text: str) -> None:
    doc = docs_service.documents().get(documentId=document_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    end_index = body_content[-1]["endIndex"] if body_content else 1

    requests = []
    if end_index > 1:
        requests.append(
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": 1,
                        "endIndex": end_index - 1,
                    }
                }
            }
        )

    requests.append(
        {
            "insertText": {
                "location": {"index": 1},
                "text": text,
            }
        }
    )

    docs_service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": requests},
    ).execute()


def _write_fallback_file(settings, reason: str, panel_url: str) -> Path:
    audit_dir = settings.project_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    fallback_path = audit_dir / "drive_launcher_fallback.md"

    doc_text = _build_doc_text(settings.panel_name, panel_url, settings.timezone)
    content = (
        "# Fallback Lanzador Drive\n\n"
        f"Motivo del fallback: {reason}\n\n"
        "## Script a ejecutar\n\n"
        "```powershell\n"
        "python scripts/create_drive_launcher_doc.py\n"
        "```\n\n"
        "## Contenido exacto recomendado para el documento\n\n"
        "```text\n"
        f"{doc_text}"
        "```\n"
    )

    fallback_path.write_text(content, encoding="utf-8")
    return fallback_path


def main() -> None:
    load_settings, docs_rw_scopes, drive_rw_scopes, get_google_credentials = _load_runtime_dependencies()
    settings = load_settings()
    panel_url = settings.streamlit_app_url or "PENDIENTE_CONFIGURAR_STREAMLIT_URL"

    scopes = sorted(set(drive_rw_scopes + docs_rw_scopes))
    creds = get_google_credentials(settings, scopes)
    if creds is None:
        fallback = _write_fallback_file(
            settings,
            reason="Sin credenciales de Google Drive/Docs.",
            panel_url=panel_url,
        )
        print(json.dumps({"status": "fallback", "file": str(fallback)}, ensure_ascii=False, indent=2))
        return

    try:
        drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
        docs_service = build("docs", "v1", credentials=creds, cache_discovery=False)

        spreadsheet_file = (
            drive_service.files()
            .get(fileId=settings.spreadsheet_id, fields="id,name,parents,webViewLink")
            .execute()
        )

        parents = spreadsheet_file.get("parents", [])
        if not parents:
            raise RuntimeError("La hoja no tiene carpeta padre detectable en Drive.")

        parent_folder_id = parents[0]
        document_id, document_url = _find_or_create_doc(
            drive_service=drive_service,
            docs_service=docs_service,
            parent_folder_id=parent_folder_id,
            doc_name=settings.drive_launcher_doc_name,
        )

        text = _build_doc_text(settings.panel_name, panel_url, settings.timezone)
        _replace_document_content(docs_service, document_id, text)

        print(
            json.dumps(
                {
                    "status": "ok",
                    "document_id": document_id,
                    "document_url": document_url,
                    "parent_folder_id": parent_folder_id,
                    "spreadsheet_id": settings.spreadsheet_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as exc:
        fallback = _write_fallback_file(settings, reason=str(exc), panel_url=panel_url)
        print(
            json.dumps(
                {
                    "status": "fallback",
                    "error": str(exc),
                    "file": str(fallback),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

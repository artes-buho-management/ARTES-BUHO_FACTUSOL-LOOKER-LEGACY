from __future__ import annotations

import argparse
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".venv",
}
DEFAULT_EXCLUDE_FILES = {
    ".env",
    "token_booking_authorized_user.json",
}


@dataclass
class SyncStats:
    folders_created: int = 0
    folders_reused: int = 0
    files_created: int = 0
    files_updated: int = 0
    files_skipped: int = 0


def _escape_query(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def _load_runtime_dependencies():
    import sys

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from config import load_settings
    from data_processing import DRIVE_RW_SCOPES

    return load_settings, DRIVE_RW_SCOPES


def _build_drive_service():
    load_settings, drive_rw_scopes = _load_runtime_dependencies()
    settings = load_settings()

    oauth_error: Exception | None = None
    if settings.oauth_token_file and settings.oauth_token_file.exists():
        try:
            payload = json.loads(settings.oauth_token_file.read_text(encoding="utf-8-sig"))
            oauth_creds = Credentials.from_authorized_user_info(payload, scopes=drive_rw_scopes)
            if oauth_creds.expired and oauth_creds.refresh_token:
                oauth_creds.refresh(Request())
            return build("drive", "v3", credentials=oauth_creds, cache_discovery=False)
        except Exception as exc:
            oauth_error = exc

    if settings.service_account_file and settings.service_account_file.exists():
        service_creds = ServiceAccountCredentials.from_service_account_file(
            str(settings.service_account_file),
            scopes=drive_rw_scopes,
        )
        return build("drive", "v3", credentials=service_creds, cache_discovery=False)

    details = f" Error OAuth: {oauth_error}" if oauth_error else ""
    raise RuntimeError(f"No hay credenciales validas para Google Drive.{details}")


def _find_child_folder(service, parent_id: str, folder_name: str) -> dict | None:
    escaped = _escape_query(folder_name)
    query = (
        f"'{parent_id}' in parents and trashed=false and "
        f"mimeType='{FOLDER_MIME_TYPE}' and name='{escaped}'"
    )
    response = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id,name)",
            pageSize=10,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    files = response.get("files", [])
    return files[0] if files else None


def _ensure_folder(service, parent_id: str, folder_name: str, stats: SyncStats) -> str:
    existing = _find_child_folder(service, parent_id, folder_name)
    if existing:
        stats.folders_reused += 1
        return existing["id"]

    created = (
        service.files()
        .create(
            body={"name": folder_name, "mimeType": FOLDER_MIME_TYPE, "parents": [parent_id]},
            fields="id,name",
            supportsAllDrives=True,
        )
        .execute()
    )
    stats.folders_created += 1
    return created["id"]


def _find_existing_file(service, parent_id: str, file_name: str) -> dict | None:
    escaped = _escape_query(file_name)
    query = (
        f"'{parent_id}' in parents and trashed=false and "
        f"name='{escaped}' and mimeType!='{FOLDER_MIME_TYPE}'"
    )
    response = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id,name,mimeType)",
            pageSize=10,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    files = response.get("files", [])
    return files[0] if files else None


def _upload_or_update_file(
    service,
    parent_id: str,
    local_file: Path,
    overwrite: bool,
    stats: SyncStats,
) -> None:
    existing = _find_existing_file(service, parent_id, local_file.name)
    mime_type = mimetypes.guess_type(str(local_file))[0] or "application/octet-stream"
    media = MediaFileUpload(str(local_file), mimetype=mime_type, resumable=False)

    if existing and not overwrite:
        stats.files_skipped += 1
        return

    if existing and overwrite:
        service.files().update(
            fileId=existing["id"],
            media_body=media,
            supportsAllDrives=True,
            fields="id,name",
        ).execute()
        stats.files_updated += 1
        return

    service.files().create(
        body={"name": local_file.name, "parents": [parent_id]},
        media_body=media,
        supportsAllDrives=True,
        fields="id,name",
    ).execute()
    stats.files_created += 1


def sync_project_to_drive(
    local_root: Path,
    target_folder_id: str,
    destination_name: str,
    overwrite: bool,
    include_sensitive_files: bool,
) -> SyncStats:
    service = _build_drive_service()
    stats = SyncStats()

    root_drive_id = _ensure_folder(service, target_folder_id, destination_name, stats)

    folder_map: dict[Path, str] = {Path("."): root_drive_id}
    excluded_files = set(DEFAULT_EXCLUDE_FILES)
    if include_sensitive_files:
        excluded_files.clear()

    for current_root, dirs, files in os.walk(local_root):
        current_path = Path(current_root)
        relative_dir = current_path.relative_to(local_root)
        drive_parent_id = folder_map.get(relative_dir)
        if drive_parent_id is None:
            continue

        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDE_DIRS]
        for dirname in dirs:
            child_relative = relative_dir / dirname
            child_id = _ensure_folder(service, drive_parent_id, dirname, stats)
            folder_map[child_relative] = child_id

        for filename in files:
            if filename in excluded_files:
                continue
            if filename.endswith((".pyc", ".pyo")):
                continue
            file_path = current_path / filename
            if not file_path.is_file():
                continue
            _upload_or_update_file(
                service=service,
                parent_id=drive_parent_id,
                local_file=file_path,
                overwrite=overwrite,
                stats=stats,
            )

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sincroniza el proyecto local en una carpeta de Google Drive.")
    parser.add_argument("--target-folder-id", required=True, help="ID de la carpeta destino en Google Drive.")
    parser.add_argument(
        "--local-root",
        default=".",
        help="Carpeta local a sincronizar. Por defecto, el directorio actual.",
    )
    parser.add_argument(
        "--destination-name",
        default=None,
        help="Nombre de la carpeta raiz en Drive. Por defecto, nombre de la carpeta local.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Si existe archivo con el mismo nombre, lo actualiza.",
    )
    parser.add_argument(
        "--include-sensitive-files",
        action="store_true",
        help="Incluye .env y token local (no recomendado).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    local_root = Path(args.local_root).resolve()
    if not local_root.exists():
        raise FileNotFoundError(f"No existe la ruta local: {local_root}")
    if not local_root.is_dir():
        raise NotADirectoryError(f"La ruta local no es carpeta: {local_root}")

    destination_name = args.destination_name or local_root.name
    stats = sync_project_to_drive(
        local_root=local_root,
        target_folder_id=args.target_folder_id,
        destination_name=destination_name,
        overwrite=args.overwrite,
        include_sensitive_files=args.include_sensitive_files,
    )

    print("Sincronizacion completada.")
    print(f"Carpetas creadas: {stats.folders_created}")
    print(f"Carpetas reutilizadas: {stats.folders_reused}")
    print(f"Archivos creados: {stats.files_created}")
    print(f"Archivos actualizados: {stats.files_updated}")
    print(f"Archivos omitidos (existentes): {stats.files_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

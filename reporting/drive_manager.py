from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import Settings
from data_processing import DRIVE_RW_SCOPES, get_google_credentials


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
PDF_MIME_TYPE = "application/pdf"


@dataclass
class ReportFolderStructure:
    parent_folder_id: str
    informes_folder_id: str
    weekly_folder_id: str
    monthly_folder_id: str
    annual_folder_id: str


@dataclass
class UploadResult:
    uploaded: bool
    skipped: bool
    overwrite: bool
    file_id: str | None
    file_name: str
    folder_id: str
    message: str


class DriveBackend(Protocol):
    def get_file(self, file_id: str, fields: str) -> dict: ...

    def find_child_folder(self, parent_id: str, folder_name: str) -> dict | None: ...

    def create_folder(self, parent_id: str, folder_name: str) -> dict: ...

    def find_file(self, parent_id: str, file_name: str, mime_type: str | None = None) -> list[dict]: ...

    def create_file(self, parent_id: str, file_name: str, local_path: Path, mime_type: str) -> dict: ...

    def update_file(self, file_id: str, local_path: Path, mime_type: str) -> dict: ...


class GoogleDriveBackend:
    def __init__(self, credentials):
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("'", "\\'")

    def get_file(self, file_id: str, fields: str) -> dict:
        return (
            self._service.files()
            .get(
                fileId=file_id,
                fields=fields,
                supportsAllDrives=True,
            )
            .execute()
        )

    def find_child_folder(self, parent_id: str, folder_name: str) -> dict | None:
        escaped = self._escape(folder_name)
        query = (
            f"'{parent_id}' in parents and trashed=false and "
            f"mimeType='{FOLDER_MIME_TYPE}' and name='{escaped}'"
        )
        response = (
            self._service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id,name,parents,driveId)",
                pageSize=5,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        files = response.get("files", [])
        return files[0] if files else None

    def create_folder(self, parent_id: str, folder_name: str) -> dict:
        body = {
            "name": folder_name,
            "mimeType": FOLDER_MIME_TYPE,
            "parents": [parent_id],
        }
        return (
            self._service.files()
            .create(
                body=body,
                fields="id,name,parents,driveId",
                supportsAllDrives=True,
            )
            .execute()
        )

    def find_file(self, parent_id: str, file_name: str, mime_type: str | None = None) -> list[dict]:
        escaped = self._escape(file_name)
        mime_clause = f" and mimeType='{mime_type}'" if mime_type else ""
        query = f"'{parent_id}' in parents and trashed=false and name='{escaped}'{mime_clause}"
        response = (
            self._service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id,name,modifiedTime,parents)",
                pageSize=10,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        return response.get("files", [])

    def create_file(self, parent_id: str, file_name: str, local_path: Path, mime_type: str) -> dict:
        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=False)
        body = {"name": file_name, "parents": [parent_id]}
        return (
            self._service.files()
            .create(
                body=body,
                media_body=media,
                fields="id,name,parents,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

    def update_file(self, file_id: str, local_path: Path, mime_type: str) -> dict:
        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=False)
        return (
            self._service.files()
            .update(
                fileId=file_id,
                media_body=media,
                fields="id,name,parents,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )


class DriveReportManager:
    def __init__(self, settings: Settings, backend: DriveBackend | None = None):
        self.settings = settings
        if backend is not None:
            self.backend = backend
            return

        credentials = get_google_credentials(settings, DRIVE_RW_SCOPES)
        if credentials is None:
            raise RuntimeError(
                "No hay credenciales de Google Drive para crear carpetas/subir informes."
            )
        self.backend = GoogleDriveBackend(credentials)

    def resolve_spreadsheet_parent_folder(self, spreadsheet_id: str | None = None) -> str:
        file_id = spreadsheet_id or self.settings.spreadsheet_id
        metadata = self.backend.get_file(
            file_id=file_id,
            fields="id,name,parents,driveId",
        )
        parents = metadata.get("parents", [])
        if parents:
            return parents[0]

        drive_id = metadata.get("driveId")
        if drive_id:
            return drive_id

        raise RuntimeError(
            "No se pudo detectar carpeta padre de la hoja fuente en Drive."
        )

    def _ensure_folder(self, parent_id: str, folder_name: str) -> str:
        existing = self.backend.find_child_folder(parent_id, folder_name)
        if existing:
            return existing["id"]
        created = self.backend.create_folder(parent_id, folder_name)
        return created["id"]

    def ensure_reports_structure(self, spreadsheet_id: str | None = None) -> ReportFolderStructure:
        parent_id = self.resolve_spreadsheet_parent_folder(spreadsheet_id)

        informes_folder_id = self._ensure_folder(parent_id, self.settings.drive_reports_root_name)
        weekly_folder_id = self._ensure_folder(informes_folder_id, self.settings.drive_weekly_folder_name)
        monthly_folder_id = self._ensure_folder(informes_folder_id, self.settings.drive_monthly_folder_name)
        annual_folder_id = self._ensure_folder(informes_folder_id, self.settings.drive_annual_folder_name)

        return ReportFolderStructure(
            parent_folder_id=parent_id,
            informes_folder_id=informes_folder_id,
            weekly_folder_id=weekly_folder_id,
            monthly_folder_id=monthly_folder_id,
            annual_folder_id=annual_folder_id,
        )

    def upload_report(
        self,
        report_type: str,
        local_pdf_path: Path,
        folder_structure: ReportFolderStructure,
        overwrite: bool = False,
    ) -> UploadResult:
        normalized_type = report_type.lower().strip()
        target_folder_map = {
            "weekly": folder_structure.weekly_folder_id,
            "monthly": folder_structure.monthly_folder_id,
            "annual": folder_structure.annual_folder_id,
        }
        if normalized_type not in target_folder_map:
            raise ValueError(f"Tipo de informe no soportado: {report_type}")

        folder_id = target_folder_map[normalized_type]
        file_name = local_pdf_path.name

        existing = self.backend.find_file(folder_id, file_name, mime_type=PDF_MIME_TYPE)
        if existing and not overwrite:
            first = existing[0]
            return UploadResult(
                uploaded=False,
                skipped=True,
                overwrite=False,
                file_id=first.get("id"),
                file_name=file_name,
                folder_id=folder_id,
                message="Informe ya existente. Skip por defecto.",
            )

        if existing and overwrite:
            first = existing[0]
            updated = self.backend.update_file(first["id"], local_pdf_path, PDF_MIME_TYPE)
            return UploadResult(
                uploaded=True,
                skipped=False,
                overwrite=True,
                file_id=updated.get("id"),
                file_name=file_name,
                folder_id=folder_id,
                message="Informe existente sobrescrito por flag --overwrite.",
            )

        created = self.backend.create_file(folder_id, file_name, local_pdf_path, PDF_MIME_TYPE)
        return UploadResult(
            uploaded=True,
            skipped=False,
            overwrite=False,
            file_id=created.get("id"),
            file_name=file_name,
            folder_id=folder_id,
            message="Informe subido correctamente a Drive.",
        )

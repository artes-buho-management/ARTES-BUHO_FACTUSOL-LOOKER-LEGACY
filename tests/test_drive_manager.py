from pathlib import Path
from tempfile import TemporaryDirectory

from config import load_settings
from reporting.drive_manager import DriveReportManager


class FakeDriveBackend:
    def __init__(self):
        self._id_seq = 1
        self.file_meta = {
            "sheet123": {
                "id": "sheet123",
                "name": "Fuente",
                "parents": ["parentABC"],
                "driveId": "driveX",
            }
        }
        self.folders_by_parent: dict[str, dict[str, str]] = {}
        self.files_by_parent: dict[str, dict[str, dict]] = {}

    def _next_id(self) -> str:
        value = f"id{self._id_seq}"
        self._id_seq += 1
        return value

    def get_file(self, file_id: str, fields: str) -> dict:
        return self.file_meta[file_id]

    def find_child_folder(self, parent_id: str, folder_name: str):
        folder_map = self.folders_by_parent.get(parent_id, {})
        folder_id = folder_map.get(folder_name)
        if not folder_id:
            return None
        return {"id": folder_id, "name": folder_name, "parents": [parent_id]}

    def create_folder(self, parent_id: str, folder_name: str):
        folder_id = self._next_id()
        self.folders_by_parent.setdefault(parent_id, {})[folder_name] = folder_id
        return {"id": folder_id, "name": folder_name, "parents": [parent_id]}

    def find_file(self, parent_id: str, file_name: str, mime_type: str | None = None):
        parent_files = self.files_by_parent.get(parent_id, {})
        record = parent_files.get(file_name)
        return [record] if record else []

    def create_file(self, parent_id: str, file_name: str, local_path: Path, mime_type: str):
        file_id = self._next_id()
        record = {"id": file_id, "name": file_name, "parents": [parent_id], "path": str(local_path)}
        self.files_by_parent.setdefault(parent_id, {})[file_name] = record
        return record

    def update_file(self, file_id: str, local_path: Path, mime_type: str):
        for parent_id, files in self.files_by_parent.items():
            for _, record in files.items():
                if record["id"] == file_id:
                    record["path"] = str(local_path)
                    return record
        raise KeyError(file_id)



def _build_settings():
    settings = load_settings()
    settings.spreadsheet_id = "sheet123"
    settings.drive_reports_root_name = "Informes"
    settings.drive_weekly_folder_name = "InformeSemanal"
    settings.drive_monthly_folder_name = "InformeMensual"
    settings.drive_annual_folder_name = "InformeAnual"
    return settings



def test_drive_structure_create_and_reuse():
    backend = FakeDriveBackend()
    settings = _build_settings()
    manager = DriveReportManager(settings, backend=backend)

    structure_1 = manager.ensure_reports_structure(settings.spreadsheet_id)
    structure_2 = manager.ensure_reports_structure(settings.spreadsheet_id)

    assert structure_1.informes_folder_id == structure_2.informes_folder_id
    assert structure_1.weekly_folder_id == structure_2.weekly_folder_id
    assert structure_1.monthly_folder_id == structure_2.monthly_folder_id
    assert structure_1.annual_folder_id == structure_2.annual_folder_id



def test_drive_upload_skip_and_overwrite():
    backend = FakeDriveBackend()
    settings = _build_settings()
    manager = DriveReportManager(settings, backend=backend)
    structure = manager.ensure_reports_structure(settings.spreadsheet_id)

    with TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "260406_InformeSemanal.pdf"
        pdf_path.write_bytes(b"demo")

        first = manager.upload_report("weekly", pdf_path, structure, overwrite=False)
        second = manager.upload_report("weekly", pdf_path, structure, overwrite=False)
        third = manager.upload_report("weekly", pdf_path, structure, overwrite=True)

    assert first.uploaded is True
    assert second.skipped is True
    assert third.overwrite is True

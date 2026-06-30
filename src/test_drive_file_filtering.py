from pipeline_executor import _drive_files


class FakeDriveClient:
    def __init__(self, files):
        self.files = files

    def list_files(self, *, folder_id):
        return self.files


def test_drive_files_default_filters_to_target_month():
    files = [
        {"id": "current", "name": "google202604数理集計後_ICE納品.csv"},
        {"id": "previous", "name": "google202603数理集計後_ICE納品.csv"},
        {"id": "unrelated", "name": "notes.csv"},
    ]

    result = _drive_files(
        provider="googleplay",
        sales_yyyymm=["202604"],
        drive_request={"files": files},
        drive_client=FakeDriveClient([]),
    )

    assert [file_obj["id"] for file_obj in result] == ["current"]


def test_drive_files_can_include_outside_target_files_for_diagnostics():
    files = [
        {"id": "current", "name": "google202604数理集計後_ICE納品.csv"},
        {"id": "previous", "name": "google202603数理集計後_ICE納品.csv"},
    ]

    result = _drive_files(
        provider="googleplay",
        sales_yyyymm=["202604"],
        drive_request={"files": files, "include_outside_target_files": True},
        drive_client=FakeDriveClient([]),
    )

    assert [file_obj["id"] for file_obj in result] == ["current", "previous"]

import pytest

from src.target_month_defaults import apply_target_month_defaults


class FakeDriveClient:
    def __init__(self, files):
        self.files = files
        self.folder_ids = []

    def list_files(self, *, folder_id):
        self.folder_ids.append(folder_id)
        return self.files


def test_apply_target_month_defaults_detects_latest_googleplay_month():
    drive_client = FakeDriveClient(
        [
            {"name": "google202604数理集計後_ICE納品.csv"},
            {"name": "google202605数理集計後_J+分.csv"},
            {"name": "readme.txt"},
        ]
    )

    result = apply_target_month_defaults(
        {
            "provider": "googleplay",
            "target_month_mode": "auto_latest",
            "run_context": {"execution_mode": "full"},
        },
        drive_client=drive_client,
    )

    assert result["sales_yyyymm"] == ["202605"]
    assert drive_client.folder_ids == ["16_rLnV3HWoQJzbGmdXEN1Mg16vCAsW4l"]


def test_apply_target_month_defaults_detects_latest_apple_month_from_file_name_alias():
    drive_client = FakeDriveClient(
        [
            {"file_name": "Apple202603数理集計後_ICE納品.xlsx"},
            {"file_name": "Apple202605数理集計後_J+分.xlsx"},
        ]
    )

    result = apply_target_month_defaults(
        {
            "provider": "apple",
            "target_month_mode": "auto_latest",
        },
        drive_client=drive_client,
    )

    assert result["sales_yyyymm"] == ["202605"]
    assert drive_client.folder_ids == ["1MSyU3QZZszTqZO55z2iVe_3JcMvwWbDu"]


def test_apply_target_month_defaults_keeps_explicit_sales_month_without_drive_lookup():
    drive_client = FakeDriveClient([{"name": "google202605数理集計後_J+分.csv"}])

    result = apply_target_month_defaults(
        {
            "provider": "googleplay",
            "target_month_mode": "auto_latest",
            "sales_yyyymm": ["202604"],
        },
        drive_client=drive_client,
    )

    assert result["sales_yyyymm"] == ["202604"]
    assert drive_client.folder_ids == []


def test_apply_target_month_defaults_requires_detectable_month():
    drive_client = FakeDriveClient([{"name": "manual-note.csv"}])

    with pytest.raises(ValueError, match="could not detect a target month"):
        apply_target_month_defaults(
            {
                "provider": "apple",
                "target_month_mode": "auto_latest",
            },
            drive_client=drive_client,
        )

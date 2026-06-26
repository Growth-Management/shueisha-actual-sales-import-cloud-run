from manifest_diff import build_manifest_rows, detected_actions_by_file_id
from validation import build_validation_results


def test_build_manifest_rows_detects_new_file():
    rows = build_manifest_rows(
        provider="apple",
        sales_yyyymm=["202606"],
        drive_files=[
            {
                "id": "apple_new_001",
                "name": "202606_ICE納品.xlsx",
                "md5Checksum": "md5-new",
                "modifiedTime": "2026-06-26T10:00:00Z",
            }
        ],
    )

    assert rows[0]["detected_action"] == "new"
    assert rows[0]["delivery_type"] == "ICE納品"
    assert detected_actions_by_file_id(rows) == {"apple_new_001": "new"}


def test_build_manifest_rows_detects_duplicate_file():
    rows = build_manifest_rows(
        provider="apple",
        sales_yyyymm=["202606"],
        drive_files=[
            {
                "id": "apple_file_001",
                "name": "202606_ICE納品.xlsx",
                "md5Checksum": "md5-existing",
            }
        ],
        existing_rows=[
            {
                "provider": "apple",
                "sales_yyyymm": "202606",
                "file_id": "apple_file_001",
                "file_name": "202606_ICE納品.xlsx",
                "md5_checksum": "md5-existing",
                "delivery_type": "ICE納品",
                "is_active_after": True,
            }
        ],
    )

    assert rows[0]["detected_action"] == "duplicate"
    assert rows[0]["status_after"] == "unchanged"


def test_build_manifest_rows_detects_revised_and_superseded_file():
    rows = build_manifest_rows(
        provider="apple",
        sales_yyyymm=["202606"],
        drive_files=[
            {
                "id": "apple_file_002",
                "name": "202606_ICE納品.xlsx",
                "md5Checksum": "md5-revised",
            }
        ],
        existing_rows=[
            {
                "provider": "apple",
                "sales_yyyymm": "202606",
                "file_id": "apple_file_001",
                "file_name": "202606_ICE納品.xlsx",
                "md5_checksum": "md5-existing",
                "delivery_type": "ICE納品",
                "is_active_after": True,
            }
        ],
    )

    assert [row["detected_action"] for row in rows] == ["superseded", "revised"]
    assert rows[0]["is_active_after"] is False
    assert rows[1]["previous_file_id"] == "apple_file_001"


def test_build_manifest_rows_marks_invalid_file_and_validation_fails():
    rows = build_manifest_rows(
        provider="apple",
        sales_yyyymm=["202606"],
        drive_files=[
            {
                "id": "apple_file_003",
                "name": "202606_unknown.xlsx",
                "md5Checksum": "md5-invalid",
            }
        ],
    )
    validation_results = build_validation_results(provider="apple", sales_yyyymm=["202606"], manifest_rows=rows)

    assert rows[0]["detected_action"] == "invalid"
    assert validation_results[0]["status"] == "failed"
    assert "ICE納品 or J+分" in validation_results[0]["error_message"]

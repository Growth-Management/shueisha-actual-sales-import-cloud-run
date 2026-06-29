from io import BytesIO

from openpyxl import Workbook

from file_normalization import normalize_drive_file


def test_normalize_drive_file_passes_csv_through():
    result = normalize_drive_file(
        file_name="sales_202606.csv",
        mime_type="text/csv",
        data=b"a,b\n1,2\n",
    )

    assert result["file_name"] == "sales_202606.csv"
    assert result["content_type"] == "text/csv"
    assert result["data"] == b"a,b\n1,2\n"
    assert result["format"] == "csv"
    assert result["was_converted"] is False


def test_normalize_drive_file_converts_xlsx_to_csv():
    result = normalize_drive_file(
        file_name="202606_ICE納品.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=_workbook_bytes(),
    )

    assert result["file_name"] == "202606_ICE納品.csv"
    assert result["content_type"] == "text/csv; charset=utf-8"
    assert result["data"] == b"store,sales\napple,1200\n"
    assert result["format"] == "csv"
    assert result["was_converted"] is True


def test_normalize_drive_file_rejects_unsupported_format():
    try:
        normalize_drive_file(file_name="sales_202606.xls", mime_type=None, data=b"legacy")
    except ValueError as exc:
        assert "unsupported file format" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def _workbook_bytes():
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["store", "sales"])
    worksheet.append(["apple", 1200])
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()

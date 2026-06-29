from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any


CSV_CONTENT_TYPE = "text/csv; charset=utf-8"


def normalize_drive_file(
    *,
    file_name: str,
    mime_type: str | None,
    data: bytes,
) -> dict[str, Any]:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv" or (mime_type or "").lower() == "text/csv":
        return {
            "file_name": file_name,
            "content_type": mime_type or CSV_CONTENT_TYPE,
            "data": data,
            "format": "csv",
            "was_converted": False,
        }
    if suffix in {".xlsx", ".xlsm"}:
        return {
            "file_name": f"{Path(file_name).stem}.csv",
            "content_type": CSV_CONTENT_TYPE,
            "data": _xlsx_to_csv(data),
            "format": "csv",
            "was_converted": True,
        }
    raise ValueError(f"unsupported file format for BigQuery load: {file_name}")


def _xlsx_to_csv(data: bytes) -> bytes:
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    worksheet = workbook.worksheets[0]
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for row in worksheet.iter_rows(values_only=True):
        writer.writerow(["" if value is None else value for value in row])
    workbook.close()
    return output.getvalue().encode("utf-8")

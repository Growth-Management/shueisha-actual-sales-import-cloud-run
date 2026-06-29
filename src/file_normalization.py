from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path
import re
from typing import Any


CSV_CONTENT_TYPE = "text/csv; charset=utf-8"

PROVIDER_RULES = {
    "apple": {
        "columns": [
            "sales_yyyymm",
            "transaction_date",
            "sku",
            "proceeds_amount",
        ],
        "required_columns": [
            "transaction_date",
            "sku",
            "proceeds_amount",
        ],
        "aliases": {
            "transaction_date": ["transaction_date", "transaction date", "date", "日付", "売上日"],
            "sku": ["sku", "product id", "product_id", "商品id", "商品ID"],
            "proceeds_amount": ["proceeds_amount", "proceeds", "developer proceeds", "amount", "売上", "金額"],
        },
        "types": {
            "transaction_date": "date",
            "proceeds_amount": "decimal",
        },
    },
    "googleplay": {
        "columns": [
            "sales_yyyymm",
            "transaction_date",
            "package_name",
            "sku",
            "developer_proceeds",
        ],
        "required_columns": [
            "transaction_date",
            "package_name",
            "developer_proceeds",
        ],
        "aliases": {
            "transaction_date": ["transaction_date", "transaction date", "date", "日付"],
            "package_name": ["package_name", "package name", "package", "app package", "アプリパッケージ"],
            "sku": ["sku", "product id", "product_id", "商品id", "商品ID"],
            "developer_proceeds": ["developer_proceeds", "developer proceeds", "proceeds", "amount", "売上", "金額"],
        },
        "types": {
            "transaction_date": "date",
            "developer_proceeds": "decimal",
        },
    },
}


def normalize_drive_file(
    *,
    provider: str,
    sales_yyyymm: str | None,
    file_name: str,
    mime_type: str | None,
    data: bytes,
) -> dict[str, Any]:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv" or (mime_type or "").lower() == "text/csv":
        normalized_data = _normalize_rows(
            provider=provider,
            sales_yyyymm=sales_yyyymm,
            rows=_csv_rows(data),
        )
        return {
            "file_name": file_name,
            "content_type": CSV_CONTENT_TYPE,
            **normalized_data,
            "format": "csv",
            "was_converted": False,
        }
    if suffix in {".xlsx", ".xlsm"}:
        normalized_data = _normalize_rows(
            provider=provider,
            sales_yyyymm=sales_yyyymm,
            rows=_xlsx_rows(data),
        )
        return {
            "file_name": f"{Path(file_name).stem}.csv",
            "content_type": CSV_CONTENT_TYPE,
            **normalized_data,
            "format": "csv",
            "was_converted": True,
        }
    raise ValueError(f"unsupported file format for BigQuery load: {file_name}")


def _normalize_rows(*, provider: str, sales_yyyymm: str | None, rows: list[list[Any]]) -> dict[str, Any]:
    rule = PROVIDER_RULES.get(provider)
    if rule is None:
        raise ValueError("provider must be apple or googleplay")

    header_index, column_map = _find_header(rows, rule)
    body_rows = [
        _normalized_record(
            row=row,
            sales_yyyymm=sales_yyyymm,
            rule=rule,
            column_map=column_map,
        )
        for row in rows[header_index + 1 :]
        if _has_values(row)
    ]

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=rule["columns"], lineterminator="\n")
    writer.writeheader()
    for record in body_rows:
        writer.writerow(record)
    return {
        "data": output.getvalue().encode("utf-8"),
        "columns": rule["columns"],
        "row_count": len(body_rows),
        "header_row_index": header_index,
    }


def _find_header(rows: list[list[Any]], rule: dict[str, Any]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows):
        normalized_cells = [_normalize_header(value) for value in row]
        column_map: dict[str, int] = {}
        for canonical, aliases in rule["aliases"].items():
            alias_set = {_normalize_header(alias) for alias in aliases}
            for column_index, cell in enumerate(normalized_cells):
                if cell in alias_set:
                    column_map[canonical] = column_index
                    break
        missing = [column for column in rule["required_columns"] if column not in column_map]
        if not missing:
            return index, column_map
    raise ValueError(f"required columns are missing: {', '.join(rule['required_columns'])}")


def _normalized_record(
    *,
    row: list[Any],
    sales_yyyymm: str | None,
    rule: dict[str, Any],
    column_map: dict[str, int],
) -> dict[str, Any]:
    record: dict[str, Any] = {"sales_yyyymm": sales_yyyymm or ""}
    for column in rule["columns"]:
        if column == "sales_yyyymm":
            continue
        value = row[column_map[column]] if column in column_map and column_map[column] < len(row) else None
        record[column] = _coerce_value(value, rule["types"].get(column))
    return record


def _coerce_value(value: Any, value_type: str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        value = value.strip()
    if value == "":
        return ""
    if value_type == "date":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        return text
    if value_type == "decimal":
        text = re.sub(r"[,¥$ ]", "", str(value).strip())
        if text.startswith("(") and text.endswith(")"):
            text = f"-{text[1:-1]}"
        try:
            return str(Decimal(text))
        except InvalidOperation:
            return str(value).strip()
    return str(value).strip()


def _csv_rows(data: bytes) -> list[list[Any]]:
    text = _decode_csv(data)
    return [row for row in csv.reader(StringIO(text))]


def _decode_csv(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def _xlsx_rows(data: bytes) -> list[list[Any]]:
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    worksheet = workbook.worksheets[0]
    try:
        return [list(row) for row in worksheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _normalize_header(value: Any) -> str:
    return re.sub(r"[\s_\-]+", " ", str(value or "").strip().lower())


def _has_values(row: list[Any]) -> bool:
    return any(str(value).strip() for value in row if value is not None)

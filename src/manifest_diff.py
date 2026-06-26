from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


TARGET_MONTH_RE = re.compile(r"(?<!\d)(20\d{4})(?!\d)")


def build_manifest_rows(
    *,
    provider: str,
    sales_yyyymm: list[str],
    drive_files: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if provider not in {"apple", "googleplay"}:
        raise ValueError("provider must be apple or googleplay")
    if not isinstance(sales_yyyymm, list):
        raise ValueError("sales_yyyymm must be a list")

    existing_rows = existing_rows or []
    active_rows = [row for row in existing_rows if row.get("is_active_after") is True or row.get("is_active") is True]
    records: list[dict[str, Any]] = []
    superseded_keys: set[tuple[str | None, str | None]] = set()

    for file_obj in drive_files:
        record = _record_for_drive_file(provider=provider, sales_yyyymm=sales_yyyymm, file_obj=file_obj)
        if record["detected_action"] != "invalid":
            action, rows_to_supersede = _detect_action(record, active_rows)
            record["detected_action"] = action
            record["status_after"] = "detected" if action in {"new", "revised"} else "unchanged"
            record["is_active_after"] = action in {"new", "revised", "duplicate"}
            record["previous_file_id"] = rows_to_supersede[0].get("file_id") if rows_to_supersede else None

            if action == "revised":
                for previous in rows_to_supersede:
                    key = (previous.get("file_id"), previous.get("md5_checksum"))
                    if key in superseded_keys:
                        continue
                    superseded_keys.add(key)
                    records.append(_superseded_record(previous))

        records.append(record)

    return records


def detected_actions_by_file_id(manifest_rows: list[dict[str, Any]]) -> dict[str, str]:
    actions: dict[str, str] = {}
    for row in manifest_rows:
        file_id = row.get("file_id")
        action = row.get("detected_action")
        if file_id and action in {"new", "revised", "duplicate", "invalid"}:
            actions[str(file_id)] = str(action)
    return actions


def _record_for_drive_file(*, provider: str, sales_yyyymm: list[str], file_obj: dict[str, Any]) -> dict[str, Any]:
    file_id = _value(file_obj, "id", "file_id")
    file_name = _value(file_obj, "name", "file_name")
    checksum = _value(file_obj, "md5Checksum", "md5_checksum")
    detected_month = _sales_month(file_name)
    delivery_type = _delivery_type(provider, file_name)
    error_message = _file_error(
        provider=provider,
        target_months=sales_yyyymm,
        file_id=file_id,
        file_name=file_name,
        checksum=checksum,
        detected_month=detected_month,
        delivery_type=delivery_type,
    )

    return {
        "provider": provider,
        "sales_yyyymm": detected_month,
        "file_id": file_id,
        "file_name": file_name,
        "md5_checksum": checksum,
        "mime_type": _value(file_obj, "mimeType", "mime_type"),
        "last_modified_at": _value(file_obj, "modifiedTime", "last_modified_at"),
        "delivery_type": delivery_type,
        "detected_action": "invalid" if error_message else "new",
        "status_after": "rejected" if error_message else "detected",
        "is_active_after": error_message is None,
        "error_message": error_message,
    }


def _detect_action(record: dict[str, Any], active_rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    checksum = record.get("md5_checksum")
    file_id = record.get("file_id")
    provider = record.get("provider")
    month = record.get("sales_yyyymm")
    delivery_type = record.get("delivery_type")

    for row in active_rows:
        if row.get("provider") != provider:
            continue
        if row.get("file_id") == file_id or (checksum and row.get("md5_checksum") == checksum):
            return "duplicate", []

    comparable_rows = [
        row
        for row in active_rows
        if row.get("provider") == provider
        and row.get("sales_yyyymm") == month
        and _existing_delivery_type(provider, row) == delivery_type
    ]
    if comparable_rows:
        return "revised", comparable_rows

    return "new", []


def _superseded_record(previous: dict[str, Any]) -> dict[str, Any]:
    record = deepcopy(previous)
    record["detected_action"] = "superseded"
    record["status_after"] = "superseded"
    record["is_active_after"] = False
    return record


def _file_error(
    *,
    provider: str,
    target_months: list[str],
    file_id: str | None,
    file_name: str | None,
    checksum: str | None,
    detected_month: str | None,
    delivery_type: str | None,
) -> str | None:
    if not file_id:
        return "Drive file id is missing"
    if not file_name:
        return "Drive file name is missing"
    if not detected_month:
        return "sales_yyyymm could not be inferred from file name"
    if detected_month not in target_months:
        return f"sales_yyyymm {detected_month} is outside target months"
    if not checksum:
        return "md5 checksum is missing"
    if provider == "apple" and delivery_type not in {"ICE納品", "J+分"}:
        return "Apple file name must include ICE納品 or J+分"
    return None


def _sales_month(file_name: str | None) -> str | None:
    if not file_name:
        return None
    match = TARGET_MONTH_RE.search(file_name)
    return match.group(1) if match else None


def _delivery_type(provider: str, file_name: str | None) -> str | None:
    if provider == "googleplay":
        return "monthly_split"
    if not file_name:
        return None
    if "J+分" in file_name:
        return "J+分"
    if "ICE納品" in file_name:
        return "ICE納品"
    return None


def _existing_delivery_type(provider: str, row: dict[str, Any]) -> str | None:
    return row.get("delivery_type") or _delivery_type(provider, row.get("file_name"))


def _value(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source[key]
    return None

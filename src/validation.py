from __future__ import annotations

from typing import Any


def build_validation_results(
    *,
    provider: str,
    sales_yyyymm: list[str],
    manifest_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if provider not in {"apple", "googleplay"}:
        raise ValueError("provider must be apple or googleplay")
    if not isinstance(sales_yyyymm, list):
        raise ValueError("sales_yyyymm must be a list")

    results: list[dict[str, Any]] = []
    for row in manifest_rows:
        action = row.get("detected_action")
        if action == "superseded":
            continue

        errors = _row_errors(provider=provider, target_months=sales_yyyymm, row=row)
        results.append(
            {
                "file_id": row.get("file_id"),
                "file_name": row.get("file_name"),
                "sales_yyyymm": row.get("sales_yyyymm"),
                "detected_action": action,
                "status": "failed" if errors else "success",
                "error_message": "; ".join(errors) if errors else None,
            }
        )

    return results


def _row_errors(*, provider: str, target_months: list[str], row: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if row.get("detected_action") == "invalid" and row.get("error_message"):
        errors.append(str(row["error_message"]))
    if not row.get("file_id"):
        errors.append("file_id is required")
    if not row.get("file_name"):
        errors.append("file_name is required")
    if not row.get("sales_yyyymm"):
        errors.append("sales_yyyymm is required")
    elif row.get("sales_yyyymm") not in target_months:
        errors.append("sales_yyyymm is outside target months")
    if not row.get("md5_checksum"):
        errors.append("md5_checksum is required")
    if provider == "apple" and row.get("delivery_type") not in {"ICE納品", "J+分"}:
        errors.append("Apple delivery_type must be ICE納品 or J+分")
    if provider == "googleplay" and row.get("delivery_type") != "monthly_split":
        errors.append("Google Play delivery_type must be monthly_split")

    return _dedupe(errors)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_V1_DIR = REPO_ROOT / "integration" / "payload_v1"
if str(PAYLOAD_V1_DIR) not in sys.path:
    sys.path.insert(0, str(PAYLOAD_V1_DIR))

from payload_builder import PROVIDER_CONFIG, delivery_type_for_file  # noqa: E402


def adapt_drive_result(provider: str, detected_files: list[dict[str, Any]]) -> dict[str, Any]:
    if provider not in PROVIDER_CONFIG:
        raise ValueError("provider must be apple or googleplay")
    if not isinstance(detected_files, list):
        raise ValueError("detected_files must be a list")

    normalized_files: list[dict[str, Any]] = []
    for file_result in detected_files:
        if not isinstance(file_result, dict):
            raise ValueError("each detected file must be a JSON object")

        file_name = file_result.get("file_name")
        if not isinstance(file_name, str):
            raise ValueError("detected file file_name is required")

        normalized = deepcopy(file_result)
        normalized.setdefault("delivery_type", delivery_type_for_file(provider, file_name))
        normalized_files.append(normalized)

    return {
        "folder_url": PROVIDER_CONFIG[provider]["folder_url"],
        "detected_files": normalized_files,
    }


def adapt_manifest_result(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(records, list):
        raise ValueError("manifest records must be a list")

    diff_summary = {
        "new_count": 0,
        "revised_count": 0,
        "duplicate_count": 0,
        "superseded_count": 0,
        "rejected_count": 0,
    }
    normalized_records: list[dict[str, Any]] = []

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each manifest record must be a JSON object")

        normalized = deepcopy(record)
        action = normalized.get("detected_action")
        status_after = normalized.get("status_after")

        if action == "new":
            diff_summary["new_count"] += 1
        elif action == "revised":
            diff_summary["revised_count"] += 1
        elif action == "duplicate":
            diff_summary["duplicate_count"] += 1
        elif action == "superseded":
            diff_summary["superseded_count"] += 1

        if action == "invalid" or status_after == "rejected":
            diff_summary["rejected_count"] += 1

        normalized_records.append(normalized)

    return {
        "has_new_or_revised_files": diff_summary["new_count"] > 0 or diff_summary["revised_count"] > 0,
        "diff_summary": diff_summary,
        "records": normalized_records,
    }


def adapt_validation_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(results, list):
        raise ValueError("validation results must be a list")

    failed_count = sum(1 for result in results if result.get("status") == "failed")
    passed_count = sum(1 for result in results if result.get("status") == "success")

    if failed_count > 0 and passed_count > 0:
        status = "partial_success"
    elif failed_count > 0:
        status = "failed"
    elif results:
        status = "success"
    else:
        status = "not_started"

    return {
        "status": status,
        "checked_file_count": len(results),
        "passed_file_count": passed_count,
        "failed_file_count": failed_count,
        "results": deepcopy(results),
    }


def adapt_staging_result(
    *,
    provider: str,
    load_jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    if provider not in PROVIDER_CONFIG:
        raise ValueError("provider must be apple or googleplay")
    if not isinstance(load_jobs, list):
        raise ValueError("load_jobs must be a list")

    failed_count = sum(1 for job in load_jobs if job.get("status") == "failed")
    success_count = sum(1 for job in load_jobs if job.get("status") == "success")
    loaded_sales_yyyymm = sorted(
        {
            str(job["sales_yyyymm"])
            for job in load_jobs
            if job.get("status") == "success" and job.get("sales_yyyymm") is not None
        }
    )
    total_loaded_row_count = sum(int(job.get("loaded_row_count") or 0) for job in load_jobs)

    if failed_count > 0 and success_count > 0:
        status = "partial_success"
    elif failed_count > 0:
        status = "failed"
    elif load_jobs:
        status = "success"
    else:
        status = "not_started"

    return {
        "status": status,
        "dataset": PROVIDER_CONFIG[provider]["staging_dataset"],
        "table": PROVIDER_CONFIG[provider]["staging_table"],
        "load_jobs": deepcopy(load_jobs),
        "loaded_sales_yyyymm": loaded_sales_yyyymm,
        "total_loaded_row_count": total_loaded_row_count,
    }


def adapt_promotion_result(
    *,
    provider: str,
    target_sales_yyyymm: list[str],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    if provider not in PROVIDER_CONFIG:
        raise ValueError("provider must be apple or googleplay")
    if not isinstance(operations, list):
        raise ValueError("promotion operations must be a list")

    failed_count = sum(1 for operation in operations if operation.get("status") == "failed")
    success_count = sum(1 for operation in operations if operation.get("status") == "success")

    if failed_count > 0 and success_count > 0:
        status = "partial_success"
    elif failed_count > 0:
        status = "failed"
    elif operations:
        status = "success"
    else:
        status = "not_started"

    return {
        "status": status,
        "dataset": PROVIDER_CONFIG[provider]["production_dataset"],
        "table": PROVIDER_CONFIG[provider]["production_table"],
        "target_sales_yyyymm": target_sales_yyyymm,
        "operations": deepcopy(operations),
        "total_deleted_row_count": sum(int(operation.get("deleted_row_count") or 0) for operation in operations),
        "total_inserted_row_count": sum(int(operation.get("inserted_row_count") or 0) for operation in operations),
    }


def adapt_verification_result(checks: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(checks, list):
        raise ValueError("verification checks must be a list")

    failed_count = sum(1 for check in checks if check.get("status") == "failed")
    passed_count = sum(1 for check in checks if check.get("status") == "passed")

    if failed_count > 0 and passed_count > 0:
        status = "partial_success"
    elif failed_count > 0:
        status = "failed"
    elif checks:
        status = "success"
    else:
        status = "not_started"

    return {
        "status": status,
        "checks": deepcopy(checks),
    }


def adapt_trocco_result(
    *,
    api_called: bool,
    api_succeeded: bool = False,
    job_id: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "api_called": api_called,
        "api_succeeded": api_succeeded,
        "job_id": job_id,
        "error_message": error_message,
    }


def adapt_webhook_result(
    *,
    status: str,
    sent_at: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "include_webhook_notification": True,
        "webhook_status": status,
        "webhook_sent_at": sent_at,
        "webhook_error_message": error_message,
    }

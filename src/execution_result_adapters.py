from __future__ import annotations

from typing import Any

from run_result_adapters import (
    adapt_drive_result,
    adapt_manifest_result,
    adapt_promotion_result,
    adapt_staging_result,
    adapt_trocco_result,
    adapt_validation_result,
    adapt_verification_result,
    adapt_webhook_result,
)


def _get_value(source: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(source, dict) and name in source:
            return source[name]
        if hasattr(source, name):
            return getattr(source, name)
    return default


def _first_value(source: Any, paths: list[tuple[str, ...]], default: Any = None) -> Any:
    for path in paths:
        current = source
        found = True
        for name in path:
            current = _get_value(current, name, default=None)
            if current is None:
                found = False
                break
        if found:
            return current
    return default


def drive_api_files_to_drive_result(
    *,
    provider: str,
    files: list[Any],
    detected_actions_by_file_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    detected_actions_by_file_id = detected_actions_by_file_id or {}
    detected_files: list[dict[str, Any]] = []

    for file_obj in files:
        file_id = _get_value(file_obj, "id", "file_id")
        file_name = _get_value(file_obj, "name", "file_name")
        if not file_id or not file_name:
            raise ValueError("Drive file result must include id/name")

        detected_files.append(
            {
                "file_id": file_id,
                "file_name": file_name,
                "mime_type": _get_value(file_obj, "mimeType", "mime_type"),
                "md5_checksum": _get_value(file_obj, "md5Checksum", "md5_checksum"),
                "last_modified_at": _get_value(file_obj, "modifiedTime", "last_modified_at"),
                "detected_action": detected_actions_by_file_id.get(str(file_id), "new"),
            }
        )

    return adapt_drive_result(provider, detected_files)


def manifest_rows_to_manifest_diff(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return adapt_manifest_result(rows)


def validation_outputs_to_validation_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    return adapt_validation_result(results)


def bigquery_load_jobs_to_staging_result(
    *,
    provider: str,
    load_jobs: list[Any],
    file_ids_by_job_id: dict[str, str] | None = None,
    sales_yyyymm_by_job_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    file_ids_by_job_id = file_ids_by_job_id or {}
    sales_yyyymm_by_job_id = sales_yyyymm_by_job_id or {}
    normalized_jobs: list[dict[str, Any]] = []

    for job in load_jobs:
        job_id = str(_get_value(job, "job_id", "jobId", "id"))
        errors = _get_value(job, "errors", default=None)
        error_result = _get_value(job, "error_result", "errorResult", default=None)
        loaded_row_count = _get_value(job, "output_rows", "outputRows", "loaded_row_count", default=0)
        status = "failed" if errors or error_result else _get_value(job, "status", default="success")

        normalized_jobs.append(
            {
                "file_id": _get_value(job, "file_id", default=file_ids_by_job_id.get(job_id)),
                "sales_yyyymm": _get_value(job, "sales_yyyymm", default=sales_yyyymm_by_job_id.get(job_id)),
                "job_id": job_id,
                "status": status,
                "loaded_row_count": int(loaded_row_count or 0),
                "error_message": _error_message_from_result(error_result or errors),
            }
        )

    return adapt_staging_result(provider=provider, load_jobs=normalized_jobs)


def bigquery_promotion_jobs_to_promotion_result(
    *,
    provider: str,
    target_sales_yyyymm: list[str],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_operations: list[dict[str, Any]] = []

    for operation in operations:
        sales_yyyymm = operation.get("sales_yyyymm")
        delete_job = operation.get("delete_job")
        insert_job = operation.get("insert_job")
        delete_error = _job_error(delete_job)
        insert_error = _job_error(insert_job)

        normalized_operations.append(
            {
                "sales_yyyymm": sales_yyyymm,
                "deleted_row_count": _affected_rows(delete_job, operation.get("deleted_row_count")),
                "inserted_row_count": _affected_rows(insert_job, operation.get("inserted_row_count")),
                "status": "failed" if delete_error or insert_error else operation.get("status", "success"),
                "error_message": delete_error or insert_error,
            }
        )

    return adapt_promotion_result(
        provider=provider,
        target_sales_yyyymm=target_sales_yyyymm,
        operations=normalized_operations,
    )


def verification_outputs_to_verification_result(checks: list[dict[str, Any]]) -> dict[str, Any]:
    return adapt_verification_result(checks)


def trocco_api_response_to_trocco_result(response: Any) -> dict[str, Any]:
    status_code = _get_value(response, "status_code", "statusCode", default=None)
    body = _get_value(response, "json_body", "body", default=None)
    if callable(getattr(response, "json", None)):
        try:
            body = response.json()
        except Exception:
            body = body or {}
    if body is None:
        body = {}

    api_succeeded = bool(status_code is not None and 200 <= int(status_code) < 300)
    job_id = _first_value(
        body,
        [
            ("job_id",),
            ("jobId",),
            ("job", "id"),
            ("data", "job_id"),
            ("data", "id"),
        ],
    )

    return adapt_trocco_result(
        api_called=True,
        api_succeeded=api_succeeded,
        job_id=str(job_id) if job_id is not None else None,
        error_message=None if api_succeeded else _error_message_from_result(body) or f"TROCCO API returned {status_code}",
    )


def webhook_response_to_webhook_result(response: Any) -> dict[str, Any]:
    status_code = _get_value(response, "status_code", "statusCode", default=None)
    status = "sent" if status_code is not None and 200 <= int(status_code) < 300 else "failed"
    return adapt_webhook_result(
        status=status,
        sent_at=_get_value(response, "sent_at", default=None),
        error_message=None if status == "sent" else _error_message_from_result(response),
    )


def _job_error(job: Any) -> str | None:
    if job is None:
        return None
    return _error_message_from_result(_get_value(job, "error_result", "errorResult", default=None) or _get_value(job, "errors", default=None))


def _affected_rows(job: Any, fallback: Any = None) -> int:
    value = _get_value(job, "num_dml_affected_rows", "numDmlAffectedRows", "affected_rows", default=fallback)
    return int(value or 0)


def _error_message_from_result(result: Any) -> str | None:
    if result is None:
        return None
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "; ".join(filter(None, (_error_message_from_result(item) for item in result))) or None
    if isinstance(result, dict):
        for key in ("message", "error_message", "error", "detail", "details"):
            value = result.get(key)
            if isinstance(value, str):
                return value
        return str(result)
    return str(result)

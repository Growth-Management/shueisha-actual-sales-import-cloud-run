from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_V1_DIR = REPO_ROOT / "integration" / "payload_v1"
if str(PAYLOAD_V1_DIR) not in sys.path:
    sys.path.insert(0, str(PAYLOAD_V1_DIR))

from payload_builder import PROVIDER_CONFIG, TROCCO_WORKFLOW_ID  # noqa: E402
from bigquery_schema import schema_for_provider  # noqa: E402
from execution_result_connector import (  # noqa: E402
    build_agent_request_from_execution_results,
    build_run_result_from_execution_results,
)
from file_normalization import normalize_drive_file  # noqa: E402
from manifest_diff import build_manifest_rows, detected_actions_by_file_id  # noqa: E402
from pipeline_clients import (  # noqa: E402
    BigQueryClient,
    DriveClient,
    GoogleBigQueryClient,
    GoogleCloudStorageClient,
    GoogleDriveClient,
    MANIFEST_TABLE,
    StorageClient,
    TroccoApiClient,
    TroccoClient,
)
from run_result_mapper import build_payload_from_run_result  # noqa: E402
from validation import build_validation_results  # noqa: E402


EXECUTION_MODE_FULL = "full"
EXECUTION_MODE_STAGING_LOAD_ONLY = "staging_load_only"
EXECUTION_MODES = {EXECUTION_MODE_FULL, EXECUTION_MODE_STAGING_LOAD_ONLY}
TARGET_MONTH_RE = re.compile(r"(?<!\d)(20\d{4})(?!\d)")


def execute_pipeline_to_agent_request(
    request_body: dict[str, Any],
    *,
    drive_client: DriveClient | None = None,
    storage_client: StorageClient | None = None,
    bigquery_client: BigQueryClient | None = None,
    trocco_client: TroccoClient | None = None,
) -> dict[str, Any]:
    execution_result = execute_pipeline(
        request_body,
        drive_client=drive_client,
        storage_client=storage_client,
        bigquery_client=bigquery_client,
        trocco_client=trocco_client,
    )
    return build_agent_request_from_execution_results(
        execution_result,
        requested_output=request_body.get("requested_output", "run_judgment"),
        include_notification_draft=_bool_value(request_body, "include_notification_draft", True),
        include_failure_analysis=_bool_value(request_body, "include_failure_analysis", False),
    )


def execute_pipeline(
    request_body: dict[str, Any],
    *,
    drive_client: DriveClient | None = None,
    storage_client: StorageClient | None = None,
    bigquery_client: BigQueryClient | None = None,
    trocco_client: TroccoClient | None = None,
) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        raise ValueError("request body must be a JSON object")

    provider = request_body.get("provider")
    sales_yyyymm = request_body.get("sales_yyyymm")
    run_context = _required_dict(request_body, "run_context")
    execution_mode = _execution_mode(request_body)

    if provider not in PROVIDER_CONFIG:
        raise ValueError("provider must be apple or googleplay")
    if not isinstance(sales_yyyymm, list):
        raise ValueError("sales_yyyymm must be a list")
    if any(not _is_sales_yyyymm(month) for month in sales_yyyymm):
        raise ValueError("sales_yyyymm values must be YYYYMM strings")

    drive_client = drive_client or GoogleDriveClient()
    storage_client = storage_client or GoogleCloudStorageClient()
    bigquery_client = bigquery_client or GoogleBigQueryClient()
    trocco_client = trocco_client or TroccoApiClient()

    drive_request = _optional_dict(request_body, "drive") or {}
    landing_request = _optional_dict(request_body, "landing") or {}
    manifest_request = _optional_dict(request_body, "manifest") or {}
    validation_request = _optional_dict(request_body, "validation") or {}
    bigquery_request = _optional_dict(request_body, "bigquery") or {}
    webhook_request = _optional_dict(request_body, "webhook") or {}

    drive_files = _drive_files(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        drive_request=drive_request,
        drive_client=drive_client,
    )
    manifest_rows = _manifest_rows(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        drive_files=drive_files,
        manifest_request=manifest_request,
        bigquery_client=bigquery_client,
    )
    validation_results = _validation_results(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        manifest_rows=manifest_rows,
        validation_request=validation_request,
    )

    if _has_validation_failure(validation_results) or not _has_new_or_revised(manifest_rows):
        landing_uploads = []
        load_results = []
        promotion_results = []
        verification_results = []
    else:
        landing_uploads = _landing_uploads(
            provider=provider,
            sales_yyyymm=sales_yyyymm,
            drive_files=drive_files,
            manifest_rows=manifest_rows,
            landing_request=landing_request,
            drive_client=drive_client,
            storage_client=storage_client,
        )
        if _has_landing_upload_failure(landing_uploads):
            load_results = _failed_landing_load_results(landing_uploads)
            promotion_results = []
            verification_results = []
        else:
            load_jobs = _load_jobs(
                provider=provider,
                bigquery_request=bigquery_request,
                landing_uploads=landing_uploads,
            )
            load_results = bigquery_client.run_load_jobs(load_jobs)
            if not load_jobs or _has_load_failure(load_results) or execution_mode == EXECUTION_MODE_STAGING_LOAD_ONLY:
                promotion_results = []
                verification_results = []
            else:
                promotion_operations = _promotion_operations(
                    provider=provider,
                    sales_yyyymm=sales_yyyymm,
                    bigquery_request=bigquery_request,
                )
                verification_checks = _verification_checks(
                    provider=provider,
                    sales_yyyymm=sales_yyyymm,
                    bigquery_request=bigquery_request,
                )
                promotion_results = bigquery_client.run_promotion(promotion_operations)
                verification_results = bigquery_client.run_verification(verification_checks)

    execution_result = {
        "provider": provider,
        "sales_yyyymm": deepcopy(sales_yyyymm),
        "run_context": deepcopy(run_context),
        "execution_results": {
            "drive": {
                "files": drive_files,
                "detected_actions_by_file_id": _optional_dict(drive_request, "detected_actions_by_file_id")
                or detected_actions_by_file_id(manifest_rows),
            },
            "manifest": {
                "rows": manifest_rows,
            },
            "validation": {
                "results": validation_results,
            },
            "bigquery": {
                "load_jobs": load_results,
                "landing_uploads": landing_uploads,
                "target_sales_yyyymm": _list_from(bigquery_request, "target_sales_yyyymm", default=sales_yyyymm),
                "promotion_operations": promotion_results,
                "verification_checks": verification_results,
            },
            "trocco": {},
            "webhook": deepcopy(webhook_request),
        },
    }

    if execution_mode == EXECUTION_MODE_FULL and _trocco_should_run(execution_result):
        try:
            trocco_response = trocco_client.trigger_workflow(
                workflow_id=TROCCO_WORKFLOW_ID,
                payload=_optional_dict(request_body, "trocco_payload") or {},
            )
        except Exception as exc:
            trocco_response = {"status_code": 0, "body": {"message": str(exc)}}
        execution_result["execution_results"]["trocco"] = {"response": trocco_response}

    execution_result["execution_results"]["manifest"]["write_result"] = _write_manifest_rows(
        manifest_rows=manifest_rows,
        manifest_request=manifest_request,
        bigquery_client=bigquery_client,
        run_context=run_context,
    )

    return execution_result


def _drive_files(
    *,
    provider: str,
    sales_yyyymm: list[str],
    drive_request: dict[str, Any],
    drive_client: DriveClient,
) -> list[dict[str, Any]]:
    provided_files = drive_request.get("files")
    if provided_files is not None:
        if not isinstance(provided_files, list):
            raise ValueError("drive.files must be a list")
        files = provided_files
    else:
        folder_id = drive_request.get("folder_id") or _folder_id_for_provider(provider)
        files = drive_client.list_files(folder_id=folder_id)

    if drive_request.get("include_outside_target_files") is True:
        return files
    return _filter_files_for_target_months(files, sales_yyyymm)


def _filter_files_for_target_months(files: list[dict[str, Any]], sales_yyyymm: list[str]) -> list[dict[str, Any]]:
    target_months = set(sales_yyyymm)
    return [file_obj for file_obj in files if _sales_month_for_file(file_obj) in target_months]


def _sales_month_for_file(file_obj: dict[str, Any]) -> str | None:
    file_name = _file_value(file_obj, "name", "file_name")
    if not file_name:
        return None
    match = TARGET_MONTH_RE.search(str(file_name))
    return match.group(1) if match else None


def _landing_uploads(
    *,
    provider: str,
    sales_yyyymm: list[str],
    drive_files: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    landing_request: dict[str, Any],
    drive_client: DriveClient,
    storage_client: StorageClient,
) -> list[dict[str, Any]]:
    bucket = landing_request.get("bucket")
    if not bucket:
        return []

    prefix = str(landing_request.get("prefix") or "landing/drive-sales-import").strip("/")
    uploadable_file_ids = {
        row.get("file_id")
        for row in manifest_rows
        if row.get("detected_action") in {"new", "revised"} and row.get("sales_yyyymm") in sales_yyyymm
    }
    files_by_id = {str(_file_value(file_obj, "id", "file_id")): file_obj for file_obj in drive_files}
    uploads: list[dict[str, Any]] = []

    for file_id in sorted(str(file_id) for file_id in uploadable_file_ids if file_id):
        file_obj = files_by_id.get(file_id)
        if not file_obj:
            continue
        file_name = _file_value(file_obj, "name", "file_name")
        mime_type = _file_value(file_obj, "mimeType", "mime_type")
        month = _manifest_month_for_file(file_id, manifest_rows)
        object_name = "/".join(
            [
                prefix,
                provider,
                str(month or "unknown"),
                file_id,
                _safe_object_name(_normalized_object_file_name(str(file_name))),
            ]
        )
        try:
            data = drive_client.download_file(file_id=file_id)
            normalized = normalize_drive_file(
                provider=provider,
                sales_yyyymm=month,
                file_name=str(file_name),
                mime_type=mime_type,
                data=data,
            )
            gcs_uri = storage_client.upload_bytes(
                bucket_name=str(bucket),
                object_name=object_name,
                data=normalized["data"],
                content_type=normalized["content_type"],
            )
            uploads.append(
                {
                    "file_id": file_id,
                    "file_name": file_name,
                    "normalized_file_name": normalized["file_name"],
                    "normalized_format": normalized["format"],
                    "was_converted": normalized["was_converted"],
                    "normalized_columns": normalized.get("columns"),
                    "normalized_row_count": normalized.get("row_count"),
                    "header_row_index": normalized.get("header_row_index"),
                    "sales_yyyymm": month,
                    "gcs_uri": gcs_uri,
                    "bucket": bucket,
                    "object_name": object_name,
                    "status": "success",
                    "error_message": None,
                }
            )
        except Exception as exc:
            uploads.append(
                {
                    "file_id": file_id,
                    "file_name": file_name,
                    "normalized_file_name": None,
                    "normalized_format": None,
                    "was_converted": False,
                    "normalized_columns": None,
                    "normalized_row_count": 0,
                    "header_row_index": None,
                    "sales_yyyymm": month,
                    "gcs_uri": None,
                    "bucket": bucket,
                    "object_name": object_name,
                    "status": "failed",
                    "error_message": str(exc),
                }
            )

    return uploads


def _load_jobs(
    *,
    provider: str,
    bigquery_request: dict[str, Any],
    landing_uploads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    provided_jobs = _list_from(bigquery_request, "load_jobs")
    if not landing_uploads:
        return provided_jobs

    default_template = _load_job_template(provider=provider, bigquery_request=bigquery_request)
    jobs_by_file_id = {
        str(job.get("file_id")): _merge_load_job(default_template, job)
        for job in provided_jobs
        if job.get("file_id") is not None
    }
    generated_jobs: list[dict[str, Any]] = []

    for upload in landing_uploads:
        if upload.get("status") != "success":
            continue
        file_id = str(upload["file_id"])
        job = jobs_by_file_id.pop(file_id, deepcopy(default_template))
        job["file_id"] = file_id
        job["sales_yyyymm"] = upload.get("sales_yyyymm")
        job["source_uris"] = [upload["gcs_uri"]]
        generated_jobs.append(job)

    generated_jobs.extend(jobs_by_file_id.values())
    generated_jobs.extend(_merge_load_job(default_template, job) for job in provided_jobs if job.get("file_id") is None)
    return generated_jobs


def _load_job_template(*, provider: str, bigquery_request: dict[str, Any]) -> dict[str, Any]:
    override = dict(bigquery_request.get("load_job_template") or {})
    default_job_config = {
        "source_format": "CSV",
        "autodetect": False,
        "schema": schema_for_provider(provider),
        "skip_leading_rows": 1,
        "write_disposition": "WRITE_APPEND",
        "field_delimiter": ",",
        "allow_quoted_newlines": True,
        "encoding": "UTF-8",
    }
    override_job_config = dict(override.pop("job_config", {}) or {})
    return {
        "destination_table": override.pop("destination_table", _staging_table_for_provider(provider)),
        "job_config": {
            **default_job_config,
            **override_job_config,
        },
        **override,
    }


def _merge_load_job(template: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(template)
    job_copy = deepcopy(job)
    template_job_config = dict(merged.get("job_config") or {})
    job_config = dict(job_copy.pop("job_config", {}) or {})
    merged.update(job_copy)
    merged["job_config"] = {
        **template_job_config,
        **job_config,
    }
    return merged


def _promotion_operations(
    *,
    provider: str,
    sales_yyyymm: list[str],
    bigquery_request: dict[str, Any],
) -> list[dict[str, Any]]:
    provided_operations = _list_from(bigquery_request, "promotion_operations", "operations")
    if provided_operations:
        return provided_operations

    staging_table = bigquery_request.get("staging_table") or _staging_table_for_provider(provider)
    production_table = bigquery_request.get("production_table") or _production_table_for_provider(provider)
    return [
        {
            "sales_yyyymm": month,
            "delete_sql": f"DELETE FROM `{production_table}` WHERE sales_yyyymm = '{month}'",
            "insert_sql": (
                f"INSERT INTO `{production_table}` "
                f"SELECT * FROM `{staging_table}` WHERE sales_yyyymm = '{month}'"
            ),
        }
        for month in sales_yyyymm
    ]


def _verification_checks(
    *,
    provider: str,
    sales_yyyymm: list[str],
    bigquery_request: dict[str, Any],
) -> list[dict[str, Any]]:
    provided_checks = _list_from(bigquery_request, "verification_checks")
    if provided_checks:
        return provided_checks

    staging_table = bigquery_request.get("staging_table") or _staging_table_for_provider(provider)
    production_table = bigquery_request.get("production_table") or _production_table_for_provider(provider)
    return [
        {
            "name": f"production_row_count_matches_staging_{month}",
            "sales_yyyymm": month,
            "sql": (
                "SELECT "
                f"(SELECT COUNT(*) FROM `{production_table}` WHERE sales_yyyymm = '{month}') "
                "= "
                f"(SELECT COUNT(*) FROM `{staging_table}` WHERE sales_yyyymm = '{month}')"
            ),
            "expected": True,
        }
        for month in sales_yyyymm
    ]


def _has_landing_upload_failure(landing_uploads: list[dict[str, Any]]) -> bool:
    return any(upload.get("status") == "failed" for upload in landing_uploads)


def _has_load_failure(load_results: list[Any]) -> bool:
    return any(isinstance(result, dict) and result.get("status") == "failed" for result in load_results)


def _failed_landing_load_results(landing_uploads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "file_id": upload.get("file_id"),
            "sales_yyyymm": upload.get("sales_yyyymm"),
            "job_id": None,
            "status": "failed",
            "loaded_row_count": 0,
            "error_message": upload.get("error_message") or "GCS landing upload failed",
        }
        for upload in landing_uploads
        if upload.get("status") == "failed"
    ]


def _manifest_rows(
    *,
    provider: str,
    sales_yyyymm: list[str],
    drive_files: list[dict[str, Any]],
    manifest_request: dict[str, Any],
    bigquery_client: BigQueryClient,
) -> list[dict[str, Any]]:
    if "rows" in manifest_request:
        return _required_list(manifest_request, "rows", section_name="manifest")
    existing_rows = _existing_manifest_rows(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        manifest_request=manifest_request,
        bigquery_client=bigquery_client,
    )
    return build_manifest_rows(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        drive_files=drive_files,
        existing_rows=existing_rows,
    )


def _existing_manifest_rows(
    *,
    provider: str,
    sales_yyyymm: list[str],
    manifest_request: dict[str, Any],
    bigquery_client: BigQueryClient,
) -> list[dict[str, Any]]:
    if "existing_rows" in manifest_request:
        return _required_list(manifest_request, "existing_rows", section_name="manifest")
    if manifest_request.get("fetch_existing_rows", True) is False:
        return []
    return bigquery_client.fetch_manifest_existing_rows(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        table=manifest_request.get("table", MANIFEST_TABLE),
    )


def _write_manifest_rows(
    *,
    manifest_rows: list[dict[str, Any]],
    manifest_request: dict[str, Any],
    bigquery_client: BigQueryClient,
    run_context: dict[str, Any],
) -> dict[str, Any]:
    if manifest_request.get("write_enabled", True) is False:
        return {"status": "skipped", "inserted_count": 0, "table": manifest_request.get("table", MANIFEST_TABLE), "error_message": None}
    return bigquery_client.write_manifest_rows(
        manifest_rows,
        table=manifest_request.get("table", MANIFEST_TABLE),
        run_context=run_context,
    )


def _validation_results(
    *,
    provider: str,
    sales_yyyymm: list[str],
    manifest_rows: list[dict[str, Any]],
    validation_request: dict[str, Any],
) -> list[dict[str, Any]]:
    if "results" in validation_request:
        return _required_list(validation_request, "results", section_name="validation")
    return build_validation_results(provider=provider, sales_yyyymm=sales_yyyymm, manifest_rows=manifest_rows)


def _has_validation_failure(validation_results: list[dict[str, Any]]) -> bool:
    return any(result.get("status") == "failed" for result in validation_results)


def _has_new_or_revised(manifest_rows: list[dict[str, Any]]) -> bool:
    return any(row.get("detected_action") in {"new", "revised"} for row in manifest_rows)


def _trocco_should_run(execution_result: dict[str, Any]) -> bool:
    run_result = build_run_result_from_execution_results(execution_result)
    payload = build_payload_from_run_result(run_result)
    return payload["trocco"]["should_trigger"] is True


def _folder_id_for_provider(provider: str) -> str:
    folder_url = PROVIDER_CONFIG[provider]["folder_url"]
    return folder_url.rstrip("/").split("/")[-1]


def _staging_table_for_provider(provider: str) -> str:
    config = PROVIDER_CONFIG[provider]
    return f"{config['staging_dataset']}.{config['staging_table']}"


def _production_table_for_provider(provider: str) -> str:
    config = PROVIDER_CONFIG[provider]
    return f"{config['production_dataset']}.{config['production_table']}"


def _manifest_month_for_file(file_id: str, manifest_rows: list[dict[str, Any]]) -> str | None:
    for row in manifest_rows:
        if str(row.get("file_id")) == file_id:
            return row.get("sales_yyyymm")
    return None


def _safe_object_name(file_name: str) -> str:
    return file_name.replace("/", "_").replace("\\", "_")


def _normalized_object_file_name(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return f"{Path(file_name).stem}.csv"
    return file_name


def _file_value(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source[key]
    return None


def _is_sales_yyyymm(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 6 and value.isdigit()


def _execution_mode(source: dict[str, Any]) -> str:
    value = source.get("execution_mode", EXECUTION_MODE_FULL)
    if value not in EXECUTION_MODES:
        raise ValueError("execution_mode must be full or staging_load_only")
    return value


def _bool_value(source: dict[str, Any], key: str, default: bool) -> bool:
    value = source.get(key, default)
    return value if isinstance(value, bool) else default


def _required_dict(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return value


def _optional_dict(source: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = source.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return value


def _required_list(source: dict[str, Any], key: str, *, section_name: str) -> list[Any]:
    value = source.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{section_name}.{key} must be a list")
    return value


def _list_from(source: dict[str, Any], *keys: str, default: list[Any] | None = None) -> list[Any]:
    for key in keys:
        value = source.get(key)
        if value is not None:
            if not isinstance(value, list):
                raise ValueError(f"{key} must be a list")
            return value
    return deepcopy(default) if default is not None else []

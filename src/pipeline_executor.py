from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_V1_DIR = REPO_ROOT / "integration" / "payload_v1"
if str(PAYLOAD_V1_DIR) not in sys.path:
    sys.path.insert(0, str(PAYLOAD_V1_DIR))

from payload_builder import PROVIDER_CONFIG, TROCCO_WORKFLOW_ID  # noqa: E402
from execution_result_connector import (  # noqa: E402
    build_agent_request_from_execution_results,
    build_run_result_from_execution_results,
)
from pipeline_clients import (  # noqa: E402
    BigQueryClient,
    DriveClient,
    GoogleBigQueryClient,
    GoogleDriveClient,
    TroccoApiClient,
    TroccoClient,
)
from run_result_mapper import build_payload_from_run_result  # noqa: E402


def execute_pipeline_to_agent_request(
    request_body: dict[str, Any],
    *,
    drive_client: DriveClient | None = None,
    bigquery_client: BigQueryClient | None = None,
    trocco_client: TroccoClient | None = None,
) -> dict[str, Any]:
    execution_result = execute_pipeline(
        request_body,
        drive_client=drive_client,
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
    bigquery_client: BigQueryClient | None = None,
    trocco_client: TroccoClient | None = None,
) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        raise ValueError("request body must be a JSON object")

    provider = request_body.get("provider")
    sales_yyyymm = request_body.get("sales_yyyymm")
    run_context = _required_dict(request_body, "run_context")

    if provider not in PROVIDER_CONFIG:
        raise ValueError("provider must be apple or googleplay")
    if not isinstance(sales_yyyymm, list):
        raise ValueError("sales_yyyymm must be a list")

    drive_client = drive_client or GoogleDriveClient()
    bigquery_client = bigquery_client or GoogleBigQueryClient()
    trocco_client = trocco_client or TroccoApiClient()

    drive_request = _optional_dict(request_body, "drive") or {}
    manifest_request = _required_dict(request_body, "manifest")
    validation_request = _optional_dict(request_body, "validation") or {}
    bigquery_request = _optional_dict(request_body, "bigquery") or {}
    webhook_request = _optional_dict(request_body, "webhook") or {}

    drive_files = _drive_files(provider=provider, drive_request=drive_request, drive_client=drive_client)
    load_results = bigquery_client.run_load_jobs(_list_from(bigquery_request, "load_jobs"))
    promotion_results = bigquery_client.run_promotion(_list_from(bigquery_request, "promotion_operations", "operations"))
    verification_results = bigquery_client.run_verification(_list_from(bigquery_request, "verification_checks"))

    execution_result = {
        "provider": provider,
        "sales_yyyymm": deepcopy(sales_yyyymm),
        "run_context": deepcopy(run_context),
        "execution_results": {
            "drive": {
                "files": drive_files,
                "detected_actions_by_file_id": _optional_dict(drive_request, "detected_actions_by_file_id") or {},
            },
            "manifest": {
                "rows": _required_list(manifest_request, "rows", section_name="manifest"),
            },
            "validation": {
                "results": _list_from(validation_request, "results"),
            },
            "bigquery": {
                "load_jobs": load_results,
                "target_sales_yyyymm": _list_from(bigquery_request, "target_sales_yyyymm", default=sales_yyyymm),
                "promotion_operations": promotion_results,
                "verification_checks": verification_results,
            },
            "trocco": {},
            "webhook": deepcopy(webhook_request),
        },
    }

    if _trocco_should_run(execution_result):
        try:
            trocco_response = trocco_client.trigger_workflow(
                workflow_id=TROCCO_WORKFLOW_ID,
                payload=_optional_dict(request_body, "trocco_payload") or {},
            )
        except Exception as exc:
            trocco_response = {"status_code": 0, "body": {"message": str(exc)}}
        execution_result["execution_results"]["trocco"] = {"response": trocco_response}

    return execution_result


def _drive_files(*, provider: str, drive_request: dict[str, Any], drive_client: DriveClient) -> list[dict[str, Any]]:
    provided_files = drive_request.get("files")
    if provided_files is not None:
        if not isinstance(provided_files, list):
            raise ValueError("drive.files must be a list")
        return provided_files

    folder_id = drive_request.get("folder_id") or _folder_id_for_provider(provider)
    return drive_client.list_files(folder_id=folder_id)


def _trocco_should_run(execution_result: dict[str, Any]) -> bool:
    run_result = build_run_result_from_execution_results(execution_result)
    payload = build_payload_from_run_result(run_result)
    return payload["trocco"]["should_trigger"] is True


def _folder_id_for_provider(provider: str) -> str:
    folder_url = PROVIDER_CONFIG[provider]["folder_url"]
    return folder_url.rstrip("/").split("/")[-1]


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

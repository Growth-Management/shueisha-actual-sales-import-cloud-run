from __future__ import annotations

from copy import deepcopy
from typing import Any

from payload_builder import PROVIDER_CONFIG, TROCCO_WORKFLOW_ID
from pipeline_clients import BigQueryClient, GoogleBigQueryClient, TroccoApiClient, TroccoClient
from pipeline_defaults import execution_mode_from_request


EXECUTION_MODE_PROMOTION_ONLY = "promotion_only"
EXECUTION_MODE_TROCCO_ONLY = "trocco_only"
SAFE_EXECUTION_MODES = {EXECUTION_MODE_PROMOTION_ONLY, EXECUTION_MODE_TROCCO_ONLY}
LANDING_REQUIRED_EXECUTION_MODES = {"full", "staging_load_only"}


def is_safe_execution_mode(request_body: dict[str, Any]) -> bool:
    return execution_mode_from_request(request_body) in SAFE_EXECUTION_MODES


def execute_requires_landing_bucket(request_body: dict[str, Any]) -> bool:
    return execution_mode_from_request(request_body) in LANDING_REQUIRED_EXECUTION_MODES


def execute_safe_mode(
    request_body: dict[str, Any],
    *,
    bigquery_client: BigQueryClient | None = None,
    trocco_client: TroccoClient | None = None,
) -> dict[str, Any]:
    execution_mode = execution_mode_from_request(request_body)
    if execution_mode not in SAFE_EXECUTION_MODES:
        raise ValueError("execution_mode must be promotion_only or trocco_only")

    provider = request_body.get("provider")
    sales_yyyymm = request_body.get("sales_yyyymm")
    run_context = request_body.get("run_context")
    if provider not in PROVIDER_CONFIG:
        raise ValueError("provider must be apple or googleplay")
    if not isinstance(sales_yyyymm, list):
        raise ValueError("sales_yyyymm must be a list")
    if any(not _is_sales_yyyymm(month) for month in sales_yyyymm):
        raise ValueError("sales_yyyymm values must be YYYYMM strings")
    if not isinstance(run_context, dict):
        raise ValueError("run_context must be a JSON object")

    bigquery_request = _optional_dict(request_body, "bigquery") or {}
    execution_result = _empty_execution_result(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        run_context=run_context,
        webhook_request=_optional_dict(request_body, "webhook") or {},
    )

    if execution_mode == EXECUTION_MODE_PROMOTION_ONLY:
        bigquery_client = bigquery_client or GoogleBigQueryClient()
        promotion_operations = _required_list(bigquery_request, "promotion_operations", section_name="bigquery")
        verification_checks = _list_from(bigquery_request, "verification_checks")
        execution_result["execution_results"]["bigquery"]["promotion_operations"] = bigquery_client.run_promotion(
            promotion_operations
        )
        execution_result["execution_results"]["bigquery"]["verification_checks"] = bigquery_client.run_verification(
            verification_checks
        )
        return execution_result

    trocco_client = trocco_client or TroccoApiClient()
    try:
        trocco_response = trocco_client.trigger_workflow(
            workflow_id=TROCCO_WORKFLOW_ID,
            payload=_optional_dict(request_body, "trocco_payload") or {},
        )
    except Exception as exc:
        trocco_response = {"status_code": 0, "body": {"message": str(exc)}}
    execution_result["execution_results"]["trocco"] = {"response": trocco_response}
    return execution_result


def _empty_execution_result(
    *,
    provider: str,
    sales_yyyymm: list[str],
    run_context: dict[str, Any],
    webhook_request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "sales_yyyymm": deepcopy(sales_yyyymm),
        "run_context": deepcopy(run_context),
        "execution_results": {
            "drive": {
                "files": [],
                "detected_actions_by_file_id": {},
            },
            "manifest": {
                "rows": [],
                "write_result": {
                    "status": "skipped",
                    "inserted_count": 0,
                    "table": None,
                    "error_message": None,
                },
            },
            "validation": {
                "results": [],
            },
            "bigquery": {
                "load_jobs": [],
                "landing_uploads": [],
                "target_sales_yyyymm": deepcopy(sales_yyyymm),
                "promotion_operations": [],
                "verification_checks": [],
            },
            "trocco": {},
            "webhook": deepcopy(webhook_request),
        },
    }


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
            return deepcopy(value)
    return deepcopy(default) if default is not None else []


def _is_sales_yyyymm(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 6 and value.isdigit()

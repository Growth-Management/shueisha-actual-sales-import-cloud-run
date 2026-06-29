from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_V1_DIR = REPO_ROOT / "integration" / "payload_v1"
if str(PAYLOAD_V1_DIR) not in sys.path:
    sys.path.insert(0, str(PAYLOAD_V1_DIR))

from payload_builder import build_agent_request  # noqa: E402
from execution_result_adapters import (  # noqa: E402
    bigquery_load_jobs_to_staging_result,
    bigquery_promotion_jobs_to_promotion_result,
    drive_api_files_to_drive_result,
    manifest_rows_to_manifest_diff,
    trocco_api_response_to_trocco_result,
    validation_outputs_to_validation_result,
    verification_outputs_to_verification_result,
    webhook_response_to_webhook_result,
)
from run_result_adapters import adapt_trocco_result  # noqa: E402
from run_result_mapper import build_payload_from_run_result  # noqa: E402


def build_run_result_from_execution_results(execution_result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(execution_result, dict):
        raise ValueError("execution_result must be a JSON object")

    provider = execution_result.get("provider")
    sales_yyyymm = execution_result.get("sales_yyyymm")
    run_context = _required_dict(execution_result, "run_context")
    raw_results = _optional_dict(execution_result, "execution_results") or execution_result

    if not isinstance(provider, str):
        raise ValueError("provider is required")
    if not isinstance(sales_yyyymm, list):
        raise ValueError("sales_yyyymm must be a list")

    drive = _optional_dict(raw_results, "drive") or {}
    manifest = _optional_dict(raw_results, "manifest") or {}
    validation = _optional_dict(raw_results, "validation") or {}
    bigquery = _optional_dict(raw_results, "bigquery") or {}
    trocco = _optional_dict(raw_results, "trocco") or {}
    webhook = _optional_dict(raw_results, "webhook") or {}

    manifest_rows = _required_list(manifest, "rows", section_name="manifest")
    load_jobs = _list_from(bigquery, "load_jobs")
    promotion_operations = _list_from(bigquery, "promotion_operations", "operations")
    verification_checks = _list_from(bigquery, "verification_checks")

    run_result: dict[str, Any] = {
        "provider": provider,
        "sales_yyyymm": deepcopy(sales_yyyymm),
        "run_context": deepcopy(run_context),
        "drive_source": drive_api_files_to_drive_result(
            provider=provider,
            files=_list_from(drive, "files"),
            detected_actions_by_file_id=_optional_dict(drive, "detected_actions_by_file_id"),
        ),
        "manifest_diff": manifest_rows_to_manifest_diff(manifest_rows),
        "validation": validation_outputs_to_validation_result(_list_from(validation, "results")),
        "staging": bigquery_load_jobs_to_staging_result(
            provider=provider,
            load_jobs=load_jobs,
            file_ids_by_job_id=_optional_dict(bigquery, "file_ids_by_job_id"),
            sales_yyyymm_by_job_id=_optional_dict(bigquery, "sales_yyyymm_by_job_id"),
        ),
        "promotion": bigquery_promotion_jobs_to_promotion_result(
            provider=provider,
            target_sales_yyyymm=_list_from(bigquery, "target_sales_yyyymm", default=sales_yyyymm),
            operations=promotion_operations,
        ),
        "verification": verification_outputs_to_verification_result(verification_checks),
        "trocco_result": _trocco_result(trocco),
    }
    if "write_result" in manifest:
        run_result["manifest_diff"]["write_result"] = deepcopy(manifest["write_result"])

    if "response" in webhook:
        run_result.update(webhook_response_to_webhook_result(webhook["response"]))
    elif webhook.get("include_notification") is True:
        run_result["include_webhook_notification"] = True
        run_result["webhook_status"] = webhook.get("status", "not_sent")
        run_result["webhook_sent_at"] = webhook.get("sent_at")
        run_result["webhook_error_message"] = webhook.get("error_message")

    return run_result


def build_agent_request_from_execution_results(
    execution_result: dict[str, Any],
    *,
    requested_output: str = "run_judgment",
    include_notification_draft: bool = True,
    include_failure_analysis: bool = False,
) -> dict[str, Any]:
    run_result = build_run_result_from_execution_results(execution_result)
    payload = build_payload_from_run_result(run_result)
    return build_agent_request(
        payload,
        requested_output=requested_output,
        include_notification_draft=include_notification_draft,
        include_failure_analysis=include_failure_analysis,
    )


def _trocco_result(trocco: dict[str, Any]) -> dict[str, Any]:
    if "response" in trocco:
        return trocco_api_response_to_trocco_result(trocco["response"])
    if trocco.get("api_called") is True:
        return adapt_trocco_result(
            api_called=True,
            api_succeeded=trocco.get("api_succeeded") is True,
            job_id=trocco.get("job_id"),
            error_message=trocco.get("error_message"),
        )
    return adapt_trocco_result(api_called=False)


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

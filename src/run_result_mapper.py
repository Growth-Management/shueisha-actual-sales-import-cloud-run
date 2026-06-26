from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_V1_DIR = REPO_ROOT / "integration" / "payload_v1"
if str(PAYLOAD_V1_DIR) not in sys.path:
    sys.path.insert(0, str(PAYLOAD_V1_DIR))

from payload_builder import (  # noqa: E402
    build_base_payload,
    build_webhook_notification,
    finalize_payload,
    validate_payload,
)


def _require_dict(source: dict[str, Any], key: str) -> dict[str, Any]:
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


def _merge_section(payload: dict[str, Any], section_name: str, section_result: dict[str, Any] | None) -> None:
    if section_result is None:
        return
    existing = payload.get(section_name)
    if isinstance(existing, dict):
        existing.update(deepcopy(section_result))
    else:
        payload[section_name] = deepcopy(section_result)


def build_payload_from_run_result(run_result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(run_result, dict):
        raise ValueError("run_result must be a JSON object")

    provider = run_result.get("provider")
    sales_yyyymm = run_result.get("sales_yyyymm")
    run_context = _require_dict(run_result, "run_context")
    manifest_diff = _require_dict(run_result, "manifest_diff")

    if not isinstance(provider, str):
        raise ValueError("provider is required")
    if not isinstance(sales_yyyymm, list):
        raise ValueError("sales_yyyymm must be a list")

    payload = build_base_payload(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        run_context=run_context,
        has_new_or_revised_files=manifest_diff.get("has_new_or_revised_files") is True,
        diff_summary=manifest_diff.get("diff_summary"),
    )
    _merge_section(payload, "manifest_diff", manifest_diff)
    _merge_section(payload, "drive_source", _optional_dict(run_result, "drive_source"))
    _merge_section(payload, "validation", _optional_dict(run_result, "validation"))
    _merge_section(payload, "staging", _optional_dict(run_result, "staging"))
    _merge_section(payload, "promotion", _optional_dict(run_result, "promotion"))
    _merge_section(payload, "verification", _optional_dict(run_result, "verification"))

    trocco_result = _optional_dict(run_result, "trocco_result") or {}
    payload = finalize_payload(
        payload,
        trocco_api_called=trocco_result.get("api_called") is True,
        trocco_api_succeeded=trocco_result.get("api_succeeded") is True,
        trocco_job_id=trocco_result.get("job_id"),
        trocco_error_message=trocco_result.get("error_message"),
    )

    webhook_notification = _optional_dict(run_result, "webhook_notification")
    if webhook_notification is not None:
        payload["webhook_notification"] = deepcopy(webhook_notification)
    elif run_result.get("include_webhook_notification") is True:
        payload["webhook_notification"] = build_webhook_notification(
            payload,
            status=run_result.get("webhook_status", "not_sent"),
            sent_at=run_result.get("webhook_sent_at"),
            error_message=run_result.get("webhook_error_message"),
        )

    validate_payload(payload)
    return payload

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict


SCHEMA_VERSION = "1.0"
TROCCO_WORKFLOW_ID = 44652

Provider = Literal["apple", "googleplay"]
StageStatus = Literal["not_started", "success", "failed", "skipped", "partial_success"]
TroccoStatus = Literal["not_triggered", "triggered", "trigger_failed", "skipped"]

PROVIDER_CONFIG: dict[Provider, dict[str, str]] = {
    "apple": {
        "folder_url": "https://drive.google.com/drive/folders/1MSyU3QZZszTqZO55z2iVe_3JcMvwWbDu",
        "staging_dataset": "ice-sh.ice_sh_source_staging",
        "staging_table": "sh_actual_apple_data_stg",
        "production_dataset": "ice-sh.ice_sh_source",
        "production_table": "sh_actual_apple_data",
    },
    "googleplay": {
        "folder_url": "https://drive.google.com/drive/folders/16_rLnV3HWoQJzbGmdXEN1Mg16vCAsW4l",
        "staging_dataset": "ice-sh.ice_sh_source_staging",
        "staging_table": "sh_actual_googleplay_data_stg",
        "production_dataset": "ice-sh.ice_sh_source",
        "production_table": "sh_actual_googleplay_data",
    },
}

ALLOWED_STAGE_STATUSES = {"not_started", "success", "failed", "skipped", "partial_success"}
ALLOWED_TROCCO_STATUSES = {"not_triggered", "triggered", "trigger_failed", "skipped"}
ALLOWED_DETECTED_ACTIONS = {"new", "revised", "duplicate", "superseded", "invalid"}
ALLOWED_NOTIFICATION_TYPES = {
    "import_success",
    "import_success_with_revision",
    "no_new_files",
    "duplicate_only",
    "format_error",
    "staging_failed",
    "promotion_failed",
    "verification_failed",
    "trocco_triggered",
    "trocco_trigger_failed",
}


class RunContext(TypedDict):
    environment: str
    trigger_source: str
    run_id: str
    run_started_at: str
    run_finished_at: str | None
    is_test: bool


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_trocco_trigger_required(payload: dict[str, Any]) -> bool:
    return (
        payload.get("manifest_diff", {}).get("has_new_or_revised_files") is True
        and payload.get("validation", {}).get("status") == "success"
        and payload.get("staging", {}).get("status") == "success"
        and payload.get("promotion", {}).get("status") == "success"
        and payload.get("verification", {}).get("status") == "success"
    )


def trocco_not_triggered_reason(payload: dict[str, Any]) -> str | None:
    if payload.get("manifest_diff", {}).get("has_new_or_revised_files") is not True:
        return "no new or revised files"
    if payload.get("validation", {}).get("status") != "success":
        return "format validation failed"
    if payload.get("staging", {}).get("status") != "success":
        return "staging load failed"
    if payload.get("promotion", {}).get("status") != "success":
        return "production promotion failed"
    if payload.get("verification", {}).get("status") != "success":
        return "production verification failed"
    return None


def delivery_type_for_file(provider: Provider, file_name: str) -> str:
    if provider == "googleplay":
        return "monthly_split"
    if "J+分" in file_name:
        return "J+分"
    return "ICE納品"


def notification_type_for_payload(payload: dict[str, Any]) -> str:
    diff_summary = payload.get("manifest_diff", {}).get("diff_summary", {})
    has_new_or_revised = payload.get("manifest_diff", {}).get("has_new_or_revised_files") is True
    new_count = int(diff_summary.get("new_count") or 0)
    revised_count = int(diff_summary.get("revised_count") or 0)
    duplicate_count = int(diff_summary.get("duplicate_count") or 0)

    if not has_new_or_revised:
        return "duplicate_only" if duplicate_count > 0 else "no_new_files"
    if payload.get("validation", {}).get("status") != "success":
        return "format_error"
    if payload.get("staging", {}).get("status") != "success":
        return "staging_failed"
    if payload.get("promotion", {}).get("status") != "success":
        return "promotion_failed"
    if payload.get("verification", {}).get("status") != "success":
        return "verification_failed"
    if payload.get("trocco", {}).get("status") == "trigger_failed":
        return "trocco_trigger_failed"
    if revised_count > 0:
        return "import_success_with_revision"
    if new_count > 0:
        return "import_success"
    return "import_success"


def build_webhook_notification(
    payload: dict[str, Any],
    *,
    should_notify: bool = True,
    status: Literal["not_sent", "sent", "failed", "skipped"] = "not_sent",
    sent_at: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "should_notify": should_notify,
        "destination": "slack_webhook",
        "status": status,
        "sent_at": sent_at,
        "notification_type": notification_type_for_payload(payload),
        "error_message": error_message,
    }


def build_agent_request(
    payload: dict[str, Any],
    *,
    requested_output: Literal["run_judgment", "failure_analysis", "operator_notification_draft"] = "run_judgment",
    include_notification_draft: bool = True,
    include_failure_analysis: bool = False,
) -> dict[str, Any]:
    validate_payload(payload)
    return {
        "input": {
            "requested_output": requested_output,
            "include_notification_draft": include_notification_draft,
            "include_failure_analysis": include_failure_analysis,
            "payload": payload,
        }
    }


def build_base_payload(
    *,
    provider: Provider,
    sales_yyyymm: list[str],
    run_context: RunContext,
    has_new_or_revised_files: bool,
    diff_summary: dict[str, int] | None = None,
) -> dict[str, Any]:
    config = PROVIDER_CONFIG[provider]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_context": run_context,
        "provider": provider,
        "sales_yyyymm": sales_yyyymm,
        "drive_source": {
            "folder_url": config["folder_url"],
            "detected_files": [],
        },
        "manifest_diff": {
            "has_new_or_revised_files": has_new_or_revised_files,
            "diff_summary": diff_summary
            or {
                "new_count": 0,
                "revised_count": 0,
                "duplicate_count": 0,
                "superseded_count": 0,
                "rejected_count": 0,
            },
            "records": [],
        },
        "validation": {"status": "not_started"},
        "staging": {
            "status": "not_started",
            "dataset": config["staging_dataset"],
            "table": config["staging_table"],
            "load_jobs": [],
            "loaded_sales_yyyymm": [],
            "total_loaded_row_count": 0,
        },
        "promotion": {
            "status": "not_started",
            "dataset": config["production_dataset"],
            "table": config["production_table"],
            "target_sales_yyyymm": sales_yyyymm,
            "operations": [],
            "total_deleted_row_count": 0,
            "total_inserted_row_count": 0,
        },
        "verification": {"status": "not_started", "checks": []},
        "trocco": {
            "should_trigger": False,
            "trigger_preconditions_met": False,
            "workflow_id": TROCCO_WORKFLOW_ID,
            "status": "not_triggered",
            "triggered_at": None,
            "job_id": None,
            "error_message": None,
        },
    }


def finalize_payload(
    payload: dict[str, Any],
    *,
    trocco_api_called: bool = False,
    trocco_api_succeeded: bool = False,
    trocco_job_id: str | None = None,
    trocco_error_message: str | None = None,
) -> dict[str, Any]:
    finalized = deepcopy(payload)
    finalized["schema_version"] = SCHEMA_VERSION

    should_trigger = is_trocco_trigger_required(finalized)
    finalized["trocco"]["should_trigger"] = should_trigger
    finalized["trocco"]["trigger_preconditions_met"] = should_trigger
    finalized["trocco"]["workflow_id"] = TROCCO_WORKFLOW_ID

    if not should_trigger:
        finalized["trocco"]["status"] = "not_triggered"
        finalized["trocco"]["triggered_at"] = None
        finalized["trocco"]["job_id"] = None
        finalized["trocco"]["error_message"] = trocco_not_triggered_reason(finalized)
    elif trocco_api_called and trocco_api_succeeded:
        finalized["trocco"]["status"] = "triggered"
        finalized["trocco"]["triggered_at"] = finalized["trocco"].get("triggered_at") or utc_now_iso()
        finalized["trocco"]["job_id"] = trocco_job_id
        finalized["trocco"]["error_message"] = None
    elif trocco_api_called:
        finalized["trocco"]["status"] = "trigger_failed"
        finalized["trocco"]["triggered_at"] = finalized["trocco"].get("triggered_at") or utc_now_iso()
        finalized["trocco"]["job_id"] = None
        finalized["trocco"]["error_message"] = trocco_error_message or "TROCCO trigger failed"
    else:
        finalized["trocco"]["status"] = "not_triggered"
        finalized["trocco"]["triggered_at"] = None
        finalized["trocco"]["job_id"] = None
        finalized["trocco"]["error_message"] = "TROCCO API was not called"

    validate_payload(finalized)
    return finalized


def validate_payload(payload: dict[str, Any]) -> None:
    required_top_level = [
        "schema_version",
        "run_context",
        "provider",
        "sales_yyyymm",
        "manifest_diff",
        "validation",
        "staging",
        "promotion",
        "verification",
        "trocco",
    ]
    missing = [key for key in required_top_level if key not in payload]
    if missing:
        raise ValueError(f"missing required top-level fields: {', '.join(missing)}")

    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    if payload["provider"] not in PROVIDER_CONFIG:
        raise ValueError("provider must be apple or googleplay")

    if not payload["sales_yyyymm"] or not all(isinstance(v, str) for v in payload["sales_yyyymm"]):
        raise ValueError("sales_yyyymm must be a non-empty string list")

    run_context = payload["run_context"]
    for key in ["environment", "trigger_source", "run_id", "run_started_at", "run_finished_at", "is_test"]:
        if key not in run_context:
            raise ValueError(f"run_context.{key} is required")

    if not isinstance(run_context["is_test"], bool):
        raise ValueError("run_context.is_test must be boolean")

    if "has_new_or_revised_files" not in payload["manifest_diff"]:
        raise ValueError("manifest_diff.has_new_or_revised_files is required")

    if not isinstance(payload["manifest_diff"]["has_new_or_revised_files"], bool):
        raise ValueError("manifest_diff.has_new_or_revised_files must be boolean")

    for section in ["validation", "staging", "promotion", "verification"]:
        status = payload[section].get("status")
        if status not in ALLOWED_STAGE_STATUSES:
            raise ValueError(f"{section}.status has invalid value: {status}")

    trocco = payload["trocco"]
    for key in ["should_trigger", "trigger_preconditions_met", "workflow_id", "status"]:
        if key not in trocco:
            raise ValueError(f"trocco.{key} is required")

    if not isinstance(trocco["should_trigger"], bool):
        raise ValueError("trocco.should_trigger must be boolean")
    if not isinstance(trocco["trigger_preconditions_met"], bool):
        raise ValueError("trocco.trigger_preconditions_met must be boolean")
    if trocco["workflow_id"] != TROCCO_WORKFLOW_ID:
        raise ValueError(f"trocco.workflow_id must be {TROCCO_WORKFLOW_ID}")
    if trocco["status"] not in ALLOWED_TROCCO_STATUSES:
        raise ValueError(f"trocco.status has invalid value: {trocco['status']}")

    expected_should_trigger = is_trocco_trigger_required(payload)
    if trocco["should_trigger"] != expected_should_trigger:
        raise ValueError("trocco.should_trigger does not match payload preconditions")

    notification = payload.get("webhook_notification")
    if notification and notification.get("notification_type") not in ALLOWED_NOTIFICATION_TYPES:
        raise ValueError("webhook_notification.notification_type has invalid value")

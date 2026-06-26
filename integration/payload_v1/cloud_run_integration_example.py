from __future__ import annotations

from payload_builder import (
    build_agent_request,
    build_base_payload,
    build_webhook_notification,
    finalize_payload,
    utc_now_iso,
)


def build_example_cloud_run_request() -> dict:
    run_started_at = utc_now_iso()

    payload = build_base_payload(
        provider="apple",
        sales_yyyymm=["202606"],
        run_context={
            "environment": "prod",
            "trigger_source": "cloud_run_api",
            "run_id": f"{run_started_at}__apple__001",
            "run_started_at": run_started_at,
            "run_finished_at": utc_now_iso(),
            "is_test": False,
        },
        has_new_or_revised_files=True,
        diff_summary={
            "new_count": 1,
            "revised_count": 0,
            "duplicate_count": 0,
            "superseded_count": 0,
            "rejected_count": 0,
        },
    )

    payload["drive_source"]["detected_files"].append(
        {
            "file_id": "apple_file_001",
            "file_name": "202606_ICE納品.xlsx",
            "delivery_type": "ICE納品",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "md5_checksum": "md5-apple-001",
            "last_modified_at": "2026-06-26T09:58:10Z",
            "detected_action": "new",
        }
    )
    payload["validation"] = {
        "status": "success",
        "checked_file_count": 1,
        "passed_file_count": 1,
        "failed_file_count": 0,
        "results": [],
    }
    payload["staging"]["status"] = "success"
    payload["staging"]["loaded_sales_yyyymm"] = ["202606"]
    payload["staging"]["total_loaded_row_count"] = 1234
    payload["promotion"]["status"] = "success"
    payload["promotion"]["total_deleted_row_count"] = 1200
    payload["promotion"]["total_inserted_row_count"] = 1234
    payload["verification"] = {
        "status": "success",
        "checks": [
            {
                "check_name": "row_count_match",
                "status": "passed",
                "details": {
                    "staging_row_count": 1234,
                    "production_row_count": 1234,
                },
                "error_message": None,
            }
        ],
    }

    finalized = finalize_payload(
        payload,
        trocco_api_called=True,
        trocco_api_succeeded=True,
        trocco_job_id="trocco_job_001",
    )
    finalized["webhook_notification"] = build_webhook_notification(
        finalized,
        status="sent",
        sent_at=utc_now_iso(),
    )

    return build_agent_request(finalized)


if __name__ == "__main__":
    import json

    print(json.dumps(build_example_cloud_run_request(), ensure_ascii=False, indent=2))

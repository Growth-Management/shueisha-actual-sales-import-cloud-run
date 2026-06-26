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
from run_result_mapper import build_payload_from_run_result


RUN_CONTEXT = {
    "environment": "prod",
    "trigger_source": "cloud_run_api",
    "run_id": "2026-06-26T10:00:00Z__apple__001",
    "run_started_at": "2026-06-26T10:00:00Z",
    "run_finished_at": "2026-06-26T10:03:42Z",
    "is_test": False,
}


def test_adapters_build_success_run_result():
    provider = "apple"
    sales_yyyymm = ["202606"]
    manifest_record = {
        "provider": provider,
        "sales_yyyymm": "202606",
        "file_id": "apple_file_001",
        "file_name": "202606_ICE納品.xlsx",
        "md5_checksum": "md5-apple-001",
        "detected_action": "new",
        "status_after": "detected",
        "is_active_after": True,
    }

    run_result = {
        "provider": provider,
        "sales_yyyymm": sales_yyyymm,
        "run_context": RUN_CONTEXT,
        "drive_source": adapt_drive_result(
            provider,
            [
                {
                    "file_id": "apple_file_001",
                    "file_name": "202606_ICE納品.xlsx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "md5_checksum": "md5-apple-001",
                    "last_modified_at": "2026-06-26T09:58:10Z",
                    "detected_action": "new",
                }
            ],
        ),
        "manifest_diff": adapt_manifest_result([manifest_record]),
        "validation": adapt_validation_result(
            [
                {
                    "file_id": "apple_file_001",
                    "file_name": "202606_ICE納品.xlsx",
                    "status": "success",
                    "format_type": "xlsx",
                    "schema_check": "passed",
                    "required_columns_check": "passed",
                    "row_count_preview": 1234,
                    "error_message": None,
                }
            ]
        ),
        "staging": adapt_staging_result(
            provider=provider,
            load_jobs=[
                {
                    "file_id": "apple_file_001",
                    "sales_yyyymm": "202606",
                    "job_id": "bq_load_job_001",
                    "status": "success",
                    "loaded_row_count": 1234,
                    "error_message": None,
                }
            ],
        ),
        "promotion": adapt_promotion_result(
            provider=provider,
            target_sales_yyyymm=sales_yyyymm,
            operations=[
                {
                    "sales_yyyymm": "202606",
                    "deleted_row_count": 1200,
                    "inserted_row_count": 1234,
                    "status": "success",
                    "error_message": None,
                }
            ],
        ),
        "verification": adapt_verification_result(
            [
                {
                    "check_name": "row_count_match",
                    "status": "passed",
                    "details": {
                        "staging_row_count": 1234,
                        "production_row_count": 1234,
                    },
                    "error_message": None,
                }
            ]
        ),
        "trocco_result": adapt_trocco_result(
            api_called=True,
            api_succeeded=True,
            job_id="trocco_job_001",
        ),
        **adapt_webhook_result(status="sent", sent_at="2026-06-26T10:03:40Z"),
    }

    payload = build_payload_from_run_result(run_result)

    assert payload["drive_source"]["detected_files"][0]["delivery_type"] == "ICE納品"
    assert payload["manifest_diff"]["diff_summary"]["new_count"] == 1
    assert payload["staging"]["total_loaded_row_count"] == 1234
    assert payload["promotion"]["total_inserted_row_count"] == 1234
    assert payload["trocco"]["status"] == "triggered"
    assert payload["webhook_notification"]["notification_type"] == "import_success"


def test_adapter_failure_statuses():
    validation = adapt_validation_result([{"status": "failed"}])
    staging = adapt_staging_result(provider="googleplay", load_jobs=[{"status": "failed", "loaded_row_count": 0}])
    verification = adapt_verification_result([{"status": "failed"}])

    assert validation["status"] == "failed"
    assert staging["status"] == "failed"
    assert verification["status"] == "failed"

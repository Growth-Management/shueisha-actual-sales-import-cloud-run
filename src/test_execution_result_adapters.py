from execution_result_adapters import (
    bigquery_load_jobs_to_staging_result,
    bigquery_promotion_jobs_to_promotion_result,
    drive_api_files_to_drive_result,
    manifest_rows_to_manifest_diff,
    trocco_api_response_to_trocco_result,
    webhook_response_to_webhook_result,
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


class Response:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def test_execution_results_build_run_result_payload():
    provider = "apple"
    sales_yyyymm = ["202606"]
    load_job = {
        "job_id": "bq_load_job_001",
        "output_rows": 1234,
        "file_id": "apple_file_001",
        "sales_yyyymm": "202606",
    }
    delete_job = {"num_dml_affected_rows": 1200}
    insert_job = {"num_dml_affected_rows": 1234}

    run_result = {
        "provider": provider,
        "sales_yyyymm": sales_yyyymm,
        "run_context": RUN_CONTEXT,
        "drive_source": drive_api_files_to_drive_result(
            provider=provider,
            files=[
                {
                    "id": "apple_file_001",
                    "name": "202606_ICE納品.xlsx",
                    "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "md5Checksum": "md5-apple-001",
                    "modifiedTime": "2026-06-26T09:58:10Z",
                }
            ],
        ),
        "manifest_diff": manifest_rows_to_manifest_diff(
            [
                {
                    "provider": provider,
                    "sales_yyyymm": "202606",
                    "file_id": "apple_file_001",
                    "file_name": "202606_ICE納品.xlsx",
                    "md5_checksum": "md5-apple-001",
                    "detected_action": "new",
                    "status_after": "detected",
                    "is_active_after": True,
                }
            ]
        ),
        "validation": {
            "status": "success",
            "checked_file_count": 1,
            "passed_file_count": 1,
            "failed_file_count": 0,
            "results": [],
        },
        "staging": bigquery_load_jobs_to_staging_result(provider=provider, load_jobs=[load_job]),
        "promotion": bigquery_promotion_jobs_to_promotion_result(
            provider=provider,
            target_sales_yyyymm=sales_yyyymm,
            operations=[
                {
                    "sales_yyyymm": "202606",
                    "delete_job": delete_job,
                    "insert_job": insert_job,
                }
            ],
        ),
        "verification": {"status": "success", "checks": []},
        "trocco_result": trocco_api_response_to_trocco_result(Response(201, {"job_id": "trocco_job_001"})),
        **webhook_response_to_webhook_result(Response(200)),
    }

    payload = build_payload_from_run_result(run_result)

    assert payload["drive_source"]["detected_files"][0]["file_id"] == "apple_file_001"
    assert payload["staging"]["total_loaded_row_count"] == 1234
    assert payload["promotion"]["total_inserted_row_count"] == 1234
    assert payload["trocco"]["status"] == "triggered"


def test_failed_trocco_response_maps_error():
    trocco_result = trocco_api_response_to_trocco_result(Response(502, {"message": "Bad Gateway"}))

    assert trocco_result["api_called"] is True
    assert trocco_result["api_succeeded"] is False
    assert trocco_result["error_message"] == "Bad Gateway"

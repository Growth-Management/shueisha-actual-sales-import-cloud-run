from execution_result_connector import (
    build_agent_request_from_execution_results,
    build_run_result_from_execution_results,
)


RUN_CONTEXT = {
    "environment": "prod",
    "trigger_source": "cloud_run_hourly",
    "run_id": "2026-06-26T10:00:00Z__googleplay__001",
    "run_started_at": "2026-06-26T10:00:00Z",
    "run_finished_at": "2026-06-26T10:04:20Z",
    "is_test": False,
}


def _execution_result(trocco_response=None):
    trocco = {"response": trocco_response} if trocco_response is not None else {}
    return {
        "provider": "googleplay",
        "sales_yyyymm": ["202606"],
        "run_context": RUN_CONTEXT,
        "execution_results": {
            "drive": {
                "files": [
                    {
                        "id": "gp_file_001",
                        "name": "sales_202606(その1).csv",
                        "mimeType": "text/csv",
                        "md5Checksum": "md5-gp-001",
                        "modifiedTime": "2026-06-26T09:59:00Z",
                    }
                ],
                "detected_actions_by_file_id": {"gp_file_001": "new"},
            },
            "manifest": {
                "rows": [
                    {
                        "provider": "googleplay",
                        "sales_yyyymm": "202606",
                        "file_id": "gp_file_001",
                        "file_name": "sales_202606(その1).csv",
                        "md5_checksum": "md5-gp-001",
                        "detected_action": "new",
                        "status_after": "detected",
                        "is_active_after": True,
                    }
                ]
            },
            "validation": {
                "results": [
                    {
                        "file_id": "gp_file_001",
                        "file_name": "sales_202606(その1).csv",
                        "status": "success",
                    }
                ]
            },
            "bigquery": {
                "load_jobs": [
                    {
                        "job_id": "bq_load_gp_001",
                        "file_id": "gp_file_001",
                        "sales_yyyymm": "202606",
                        "output_rows": 800,
                    }
                ],
                "target_sales_yyyymm": ["202606"],
                "promotion_operations": [
                    {
                        "sales_yyyymm": "202606",
                        "delete_job": {"num_dml_affected_rows": 790},
                        "insert_job": {"num_dml_affected_rows": 800},
                    }
                ],
                "verification_checks": [
                    {
                        "name": "production_row_count_matches_staging",
                        "status": "passed",
                        "expected": 800,
                        "actual": 800,
                    }
                ],
            },
            "trocco": trocco,
            "webhook": {
                "include_notification": True,
                "status": "not_sent",
            },
        },
    }


def test_build_run_result_from_execution_results():
    run_result = build_run_result_from_execution_results(
        _execution_result({"status_code": 201, "body": {"job_id": "trocco_job_gp_001"}})
    )

    assert run_result["drive_source"]["detected_files"][0]["file_id"] == "gp_file_001"
    assert run_result["manifest_diff"]["has_new_or_revised_files"] is True
    assert run_result["staging"]["total_loaded_row_count"] == 800
    assert run_result["promotion"]["total_inserted_row_count"] == 800
    assert run_result["verification"]["status"] == "success"
    assert run_result["trocco_result"]["job_id"] == "trocco_job_gp_001"


def test_build_agent_request_from_execution_results_triggers_trocco():
    request_body = build_agent_request_from_execution_results(
        _execution_result({"status_code": 201, "body": {"job_id": "trocco_job_gp_001"}})
    )
    payload = request_body["input"]["payload"]

    assert payload["provider"] == "googleplay"
    assert payload["trocco"]["should_trigger"] is True
    assert payload["trocco"]["status"] == "triggered"
    assert payload["trocco"]["job_id"] == "trocco_job_gp_001"
    assert payload["webhook_notification"]["status"] == "not_sent"


def test_build_agent_request_without_trocco_response_keeps_not_triggered():
    request_body = build_agent_request_from_execution_results(_execution_result())
    payload = request_body["input"]["payload"]

    assert payload["trocco"]["should_trigger"] is True
    assert payload["trocco"]["status"] == "not_triggered"
    assert payload["trocco"]["error_message"] == "TROCCO API was not called"

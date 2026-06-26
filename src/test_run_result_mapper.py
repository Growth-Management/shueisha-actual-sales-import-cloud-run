from run_result_mapper import build_payload_from_run_result


RUN_CONTEXT = {
    "environment": "prod",
    "trigger_source": "cloud_run_api",
    "run_id": "2026-06-26T10:00:00Z__apple__001",
    "run_started_at": "2026-06-26T10:00:00Z",
    "run_finished_at": "2026-06-26T10:03:42Z",
    "is_test": False,
}


def test_success_run_result_maps_to_triggered_payload():
    payload = build_payload_from_run_result(
        {
            "provider": "apple",
            "sales_yyyymm": ["202606"],
            "run_context": RUN_CONTEXT,
            "manifest_diff": {
                "has_new_or_revised_files": True,
                "diff_summary": {
                    "new_count": 1,
                    "revised_count": 0,
                    "duplicate_count": 0,
                    "superseded_count": 0,
                    "rejected_count": 0,
                },
            },
            "validation": {"status": "success"},
            "staging": {"status": "success", "total_loaded_row_count": 1234},
            "promotion": {"status": "success", "total_inserted_row_count": 1234},
            "verification": {"status": "success", "checks": []},
            "trocco_result": {
                "api_called": True,
                "api_succeeded": True,
                "job_id": "trocco_job_001",
            },
            "include_webhook_notification": True,
            "webhook_status": "sent",
        }
    )

    assert payload["schema_version"] == "1.0"
    assert payload["trocco"]["should_trigger"] is True
    assert payload["trocco"]["status"] == "triggered"
    assert payload["trocco"]["job_id"] == "trocco_job_001"
    assert payload["webhook_notification"]["notification_type"] == "import_success"


def test_staging_failure_maps_to_not_triggered_payload():
    payload = build_payload_from_run_result(
        {
            "provider": "googleplay",
            "sales_yyyymm": ["202606"],
            "run_context": RUN_CONTEXT,
            "manifest_diff": {
                "has_new_or_revised_files": True,
                "diff_summary": {
                    "new_count": 1,
                    "revised_count": 0,
                    "duplicate_count": 0,
                    "superseded_count": 0,
                    "rejected_count": 0,
                },
            },
            "validation": {"status": "success"},
            "staging": {"status": "failed"},
            "promotion": {"status": "not_started"},
            "verification": {"status": "not_started"},
            "trocco_result": {"api_called": False},
        }
    )

    assert payload["trocco"]["should_trigger"] is False
    assert payload["trocco"]["status"] == "not_triggered"
    assert payload["trocco"]["error_message"] == "staging load failed"

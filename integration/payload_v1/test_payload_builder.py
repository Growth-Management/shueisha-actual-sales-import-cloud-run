from payload_builder import (
    build_agent_request,
    build_base_payload,
    build_webhook_notification,
    delivery_type_for_file,
    finalize_payload,
)


RUN_CONTEXT = {
    "environment": "prod",
    "trigger_source": "cloud_run_api",
    "run_id": "2026-06-26T10:00:00Z__apple__001",
    "run_started_at": "2026-06-26T10:00:00Z",
    "run_finished_at": "2026-06-26T10:03:42Z",
    "is_test": False,
}


def test_success_payload_triggers_trocco():
    payload = build_base_payload(
        provider="apple",
        sales_yyyymm=["202606"],
        run_context=RUN_CONTEXT,
        has_new_or_revised_files=True,
        diff_summary={
            "new_count": 1,
            "revised_count": 0,
            "duplicate_count": 0,
            "superseded_count": 0,
            "rejected_count": 0,
        },
    )
    for section in ["validation", "staging", "promotion", "verification"]:
        payload[section]["status"] = "success"

    finalized = finalize_payload(
        payload,
        trocco_api_called=True,
        trocco_api_succeeded=True,
        trocco_job_id="trocco_job_001",
    )
    finalized["webhook_notification"] = build_webhook_notification(finalized, status="sent")

    assert finalized["schema_version"] == "1.0"
    assert finalized["trocco"]["should_trigger"] is True
    assert finalized["trocco"]["status"] == "triggered"
    assert finalized["webhook_notification"]["notification_type"] == "import_success"

    request_body = build_agent_request(finalized)
    assert request_body["input"]["payload"] == finalized
    assert request_body["input"]["requested_output"] == "run_judgment"


def test_staging_failure_does_not_trigger_trocco():
    payload = build_base_payload(
        provider="googleplay",
        sales_yyyymm=["202606"],
        run_context=RUN_CONTEXT,
        has_new_or_revised_files=True,
    )
    payload["validation"]["status"] = "success"
    payload["staging"]["status"] = "failed"
    payload["promotion"]["status"] = "not_started"
    payload["verification"]["status"] = "not_started"

    finalized = finalize_payload(payload)
    finalized["webhook_notification"] = build_webhook_notification(finalized, status="sent")

    assert finalized["trocco"]["should_trigger"] is False
    assert finalized["trocco"]["status"] == "not_triggered"
    assert finalized["trocco"]["error_message"] == "staging load failed"
    assert finalized["webhook_notification"]["notification_type"] == "staging_failed"


def test_duplicate_only_notification():
    payload = build_base_payload(
        provider="apple",
        sales_yyyymm=["202606"],
        run_context=RUN_CONTEXT,
        has_new_or_revised_files=False,
        diff_summary={
            "new_count": 0,
            "revised_count": 0,
            "duplicate_count": 2,
            "superseded_count": 0,
            "rejected_count": 0,
        },
    )
    finalized = finalize_payload(payload)
    finalized["webhook_notification"] = build_webhook_notification(finalized, status="sent")

    assert finalized["trocco"]["should_trigger"] is False
    assert finalized["webhook_notification"]["notification_type"] == "duplicate_only"


def test_provider_delivery_type_mapping():
    assert delivery_type_for_file("googleplay", "202606_確報_その1.csv") == "monthly_split"
    assert delivery_type_for_file("apple", "202606_J+分.xlsx") == "J+分"
    assert delivery_type_for_file("apple", "202606_ICE納品.xlsx") == "ICE納品"

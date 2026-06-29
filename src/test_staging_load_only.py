from pipeline_executor import execute_pipeline_to_agent_request
from test_pipeline_executor import (
    FakeBigQueryClient,
    FakeDriveClient,
    FakeStorageClient,
    FakeTroccoClient,
    _request_without_manifest_or_validation,
)


def test_staging_load_only_runs_load_and_stops_before_production_steps():
    drive_client = FakeDriveClient()
    storage_client = FakeStorageClient()
    bigquery_client = FakeBigQueryClient()
    trocco_client = FakeTroccoClient()
    request = _request_without_manifest_or_validation()
    request["execution_mode"] = "staging_load_only"
    request["landing"] = {"bucket": "sales-landing", "prefix": "drive-import"}

    request_body = execute_pipeline_to_agent_request(
        request,
        drive_client=drive_client,
        storage_client=storage_client,
        bigquery_client=bigquery_client,
        trocco_client=trocco_client,
    )
    payload = request_body["input"]["payload"]

    assert drive_client.downloaded_file_ids == ["apple_file_001"]
    assert storage_client.uploads[0]["bucket_name"] == "sales-landing"
    assert bigquery_client.load_called is True
    assert bigquery_client.load_jobs[0]["destination_table"] == "ice-sh.ice_sh_source_staging.sh_actual_apple_data_stg"
    assert bigquery_client.promotion_called is False
    assert bigquery_client.verification_called is False
    assert trocco_client.calls == []
    assert payload["staging"]["status"] == "success"
    assert payload["promotion"]["status"] == "not_started"
    assert payload["verification"]["status"] == "not_started"
    assert payload["trocco"]["status"] == "not_triggered"
    assert payload["manifest_diff"]["write_result"]["status"] == "success"

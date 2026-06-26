from pipeline_executor import execute_pipeline_to_agent_request


RUN_CONTEXT = {
    "environment": "prod",
    "trigger_source": "cloud_run_hourly",
    "run_id": "2026-06-26T10:00:00Z__apple__001",
    "run_started_at": "2026-06-26T10:00:00Z",
    "run_finished_at": "2026-06-26T10:04:20Z",
    "is_test": False,
}


class FakeDriveClient:
    def __init__(self):
        self.folder_ids = []

    def list_files(self, *, folder_id):
        self.folder_ids.append(folder_id)
        return [
            {
                "id": "apple_file_001",
                "name": "202606_ICE納品.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "md5Checksum": "md5-apple-001",
                "modifiedTime": "2026-06-26T09:59:00Z",
            }
        ]


class FakeBigQueryClient:
    def run_load_jobs(self, load_jobs):
        return [
            {
                "job_id": "bq_load_001",
                "file_id": "apple_file_001",
                "sales_yyyymm": "202606",
                "output_rows": 1200,
            }
        ]

    def run_promotion(self, operations):
        return [
            {
                "sales_yyyymm": "202606",
                "delete_job": {"num_dml_affected_rows": 1190},
                "insert_job": {"num_dml_affected_rows": 1200},
            }
        ]

    def run_verification(self, checks):
        return [
            {
                "name": "production_row_count_matches_staging",
                "status": "passed",
                "expected": 1200,
                "actual": 1200,
            }
        ]


class FakeTroccoClient:
    def __init__(self):
        self.calls = []

    def trigger_workflow(self, *, workflow_id, payload):
        self.calls.append({"workflow_id": workflow_id, "payload": payload})
        return {"status_code": 201, "body": {"job_id": "trocco_job_001"}}


class FailingTroccoClient:
    def trigger_workflow(self, *, workflow_id, payload):
        raise RuntimeError("trocco unavailable")


def _request(validation_status="success"):
    return {
        "provider": "apple",
        "sales_yyyymm": ["202606"],
        "run_context": RUN_CONTEXT,
        "manifest": {
            "rows": [
                {
                    "provider": "apple",
                    "sales_yyyymm": "202606",
                    "file_id": "apple_file_001",
                    "file_name": "202606_ICE納品.xlsx",
                    "md5_checksum": "md5-apple-001",
                    "detected_action": "new",
                    "status_after": "detected",
                    "is_active_after": True,
                }
            ]
        },
        "drive": {
            "detected_actions_by_file_id": {"apple_file_001": "new"},
        },
        "validation": {
            "results": [
                {
                    "file_id": "apple_file_001",
                    "file_name": "202606_ICE納品.xlsx",
                    "status": validation_status,
                }
            ]
        },
        "bigquery": {
            "load_jobs": [
                {
                    "source_uris": ["gs://landing/apple/202606_ICE納品.xlsx"],
                    "destination_table": "ice-sh.ice_sh_source_staging.sh_actual_apple_data_stg",
                }
            ],
            "promotion_operations": [
                {
                    "sales_yyyymm": "202606",
                    "delete_sql": "DELETE FROM prod WHERE sales_yyyymm = '202606'",
                    "insert_sql": "INSERT INTO prod SELECT * FROM stg WHERE sales_yyyymm = '202606'",
                }
            ],
            "verification_checks": [
                {
                    "name": "production_row_count_matches_staging",
                    "sql": "SELECT 1200",
                    "expected": 1200,
                }
            ],
        },
        "trocco_payload": {"provider": "apple", "sales_yyyymm": ["202606"]},
    }


def test_execute_pipeline_triggers_trocco_when_preconditions_pass():
    drive_client = FakeDriveClient()
    trocco_client = FakeTroccoClient()

    request_body = execute_pipeline_to_agent_request(
        _request(),
        drive_client=drive_client,
        bigquery_client=FakeBigQueryClient(),
        trocco_client=trocco_client,
    )
    payload = request_body["input"]["payload"]

    assert drive_client.folder_ids == ["1MSyU3QZZszTqZO55z2iVe_3JcMvwWbDu"]
    assert payload["trocco"]["status"] == "triggered"
    assert payload["trocco"]["job_id"] == "trocco_job_001"
    assert trocco_client.calls[0]["workflow_id"] == 44652


def test_execute_pipeline_skips_trocco_when_validation_fails():
    trocco_client = FakeTroccoClient()

    request_body = execute_pipeline_to_agent_request(
        _request(validation_status="failed"),
        drive_client=FakeDriveClient(),
        bigquery_client=FakeBigQueryClient(),
        trocco_client=trocco_client,
    )
    payload = request_body["input"]["payload"]

    assert trocco_client.calls == []
    assert payload["validation"]["status"] == "failed"
    assert payload["trocco"]["status"] == "not_triggered"


def test_execute_pipeline_maps_trocco_exception_to_trigger_failed():
    request_body = execute_pipeline_to_agent_request(
        _request(),
        drive_client=FakeDriveClient(),
        bigquery_client=FakeBigQueryClient(),
        trocco_client=FailingTroccoClient(),
    )
    payload = request_body["input"]["payload"]

    assert payload["trocco"]["should_trigger"] is True
    assert payload["trocco"]["status"] == "trigger_failed"
    assert payload["trocco"]["error_message"] == "trocco unavailable"

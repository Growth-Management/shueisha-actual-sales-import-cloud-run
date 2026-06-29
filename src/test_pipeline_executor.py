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
        self.downloaded_file_ids = []

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

    def download_file(self, *, file_id):
        self.downloaded_file_ids.append(file_id)
        return b"file-bytes"


class FakeStorageClient:
    def __init__(self):
        self.uploads = []

    def upload_bytes(self, *, bucket_name, object_name, data, content_type=None):
        self.uploads.append(
            {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "data": data,
                "content_type": content_type,
            }
        )
        return f"gs://{bucket_name}/{object_name}"


class FailingStorageClient:
    def upload_bytes(self, *, bucket_name, object_name, data, content_type=None):
        raise RuntimeError("gcs unavailable")


class FakeBigQueryClient:
    def __init__(self):
        self.load_called = False
        self.promotion_called = False
        self.verification_called = False
        self.fetch_manifest_called = False
        self.written_manifest_rows = []
        self.load_jobs = []
        self.promotion_operations = []
        self.verification_checks = []

    def fetch_manifest_existing_rows(self, *, provider, sales_yyyymm, table="ice-sh.ice_sh_process.drive_sales_import_manifest"):
        self.fetch_manifest_called = True
        return []

    def write_manifest_rows(self, rows, *, table="ice-sh.ice_sh_process.drive_sales_import_manifest", run_context=None):
        self.written_manifest_rows = rows
        return {
            "status": "success",
            "inserted_count": len(rows),
            "table": table,
            "error_message": None,
        }

    def run_load_jobs(self, load_jobs):
        self.load_called = True
        self.load_jobs = load_jobs
        return [
            {
                "job_id": "bq_load_001",
                "file_id": "apple_file_001",
                "sales_yyyymm": "202606",
                "output_rows": 1200,
            }
        ]

    def run_promotion(self, operations):
        self.promotion_called = True
        self.promotion_operations = operations
        return [
            {
                "sales_yyyymm": "202606",
                "delete_job": {"num_dml_affected_rows": 1190},
                "insert_job": {"num_dml_affected_rows": 1200},
            }
        ]

    def run_verification(self, checks):
        self.verification_called = True
        self.verification_checks = checks
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
                    "file_id": "apple_file_001",
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


def _request_without_manifest_or_validation():
    request = _request()
    request.pop("manifest")
    request.pop("validation")
    return request


def test_execute_pipeline_triggers_trocco_when_preconditions_pass():
    drive_client = FakeDriveClient()
    storage_client = FakeStorageClient()
    bigquery_client = FakeBigQueryClient()
    trocco_client = FakeTroccoClient()

    request_body = execute_pipeline_to_agent_request(
        _request(),
        drive_client=drive_client,
        storage_client=storage_client,
        bigquery_client=bigquery_client,
        trocco_client=trocco_client,
    )
    payload = request_body["input"]["payload"]

    assert drive_client.folder_ids == ["1MSyU3QZZszTqZO55z2iVe_3JcMvwWbDu"]
    assert drive_client.downloaded_file_ids == []
    assert storage_client.uploads == []
    assert bigquery_client.load_jobs[0]["source_uris"] == ["gs://landing/apple/202606_ICE納品.xlsx"]
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


def test_execute_pipeline_builds_manifest_and_validation_results():
    drive_client = FakeDriveClient()
    storage_client = FakeStorageClient()
    bigquery_client = FakeBigQueryClient()
    request = _request_without_manifest_or_validation()
    request["landing"] = {"bucket": "sales-landing", "prefix": "drive-import"}

    request_body = execute_pipeline_to_agent_request(
        request,
        drive_client=drive_client,
        storage_client=storage_client,
        bigquery_client=bigquery_client,
        trocco_client=FakeTroccoClient(),
    )
    payload = request_body["input"]["payload"]

    assert bigquery_client.fetch_manifest_called is True
    assert bigquery_client.written_manifest_rows[0]["detected_action"] == "new"
    assert drive_client.downloaded_file_ids == ["apple_file_001"]
    assert storage_client.uploads[0]["bucket_name"] == "sales-landing"
    assert bigquery_client.load_jobs[0]["source_uris"] == [
        "gs://sales-landing/drive-import/apple/202606/apple_file_001/202606_ICE納品.xlsx"
    ]
    assert payload["manifest_diff"]["records"][0]["detected_action"] == "new"
    assert payload["manifest_diff"]["write_result"]["status"] == "success"
    assert payload["validation"]["status"] == "success"
    assert payload["drive_source"]["detected_files"][0]["detected_action"] == "new"


def test_execute_pipeline_generates_bigquery_plan_from_provider_defaults():
    drive_client = FakeDriveClient()
    storage_client = FakeStorageClient()
    bigquery_client = FakeBigQueryClient()
    request = _request_without_manifest_or_validation()
    request["landing"] = {"bucket": "sales-landing", "prefix": "drive-import"}
    request["bigquery"] = {
        "load_job_template": {
            "job_config": {
                "skip_leading_rows": 2,
            }
        }
    }

    execute_pipeline_to_agent_request(
        request,
        drive_client=drive_client,
        storage_client=storage_client,
        bigquery_client=bigquery_client,
        trocco_client=FakeTroccoClient(),
    )

    assert bigquery_client.load_jobs == [
        {
            "destination_table": "ice-sh.ice_sh_source_staging.sh_actual_apple_data_stg",
            "job_config": {
                "source_format": "CSV",
                "autodetect": True,
                "skip_leading_rows": 2,
                "write_disposition": "WRITE_APPEND",
                "field_delimiter": ",",
                "allow_quoted_newlines": True,
                "encoding": "UTF-8",
            },
            "file_id": "apple_file_001",
            "sales_yyyymm": "202606",
            "source_uris": [
                "gs://sales-landing/drive-import/apple/202606/apple_file_001/202606_ICE納品.xlsx"
            ],
        }
    ]
    assert bigquery_client.promotion_operations == [
        {
            "sales_yyyymm": "202606",
            "delete_sql": "DELETE FROM `ice-sh.ice_sh_source.sh_actual_apple_data` WHERE sales_yyyymm = '202606'",
            "insert_sql": (
                "INSERT INTO `ice-sh.ice_sh_source.sh_actual_apple_data` "
                "SELECT * FROM `ice-sh.ice_sh_source_staging.sh_actual_apple_data_stg` WHERE sales_yyyymm = '202606'"
            ),
        }
    ]
    assert bigquery_client.verification_checks == [
        {
            "name": "production_row_count_matches_staging_202606",
            "sales_yyyymm": "202606",
            "sql": (
                "SELECT "
                "(SELECT COUNT(*) FROM `ice-sh.ice_sh_source.sh_actual_apple_data` WHERE sales_yyyymm = '202606') "
                "= "
                "(SELECT COUNT(*) FROM `ice-sh.ice_sh_source_staging.sh_actual_apple_data_stg` WHERE sales_yyyymm = '202606')"
            ),
            "expected": True,
        }
    ]


def test_execute_pipeline_skips_promotion_when_no_load_job_exists():
    bigquery_client = FakeBigQueryClient()
    request = _request_without_manifest_or_validation()
    request["bigquery"] = {}

    request_body = execute_pipeline_to_agent_request(
        request,
        drive_client=FakeDriveClient(),
        storage_client=FakeStorageClient(),
        bigquery_client=bigquery_client,
        trocco_client=FakeTroccoClient(),
    )
    payload = request_body["input"]["payload"]

    assert bigquery_client.load_called is True
    assert bigquery_client.load_jobs == []
    assert bigquery_client.promotion_called is False
    assert bigquery_client.verification_called is False
    assert payload["promotion"]["status"] == "not_started"
    assert payload["verification"]["status"] == "not_started"


def test_execute_pipeline_skips_bigquery_when_generated_validation_fails():
    class InvalidDriveClient:
        def list_files(self, *, folder_id):
            return [
                {
                    "id": "apple_file_invalid",
                    "name": "202606_unknown.xlsx",
                    "md5Checksum": "md5-invalid",
                }
            ]

    bigquery_client = FakeBigQueryClient()
    request = _request_without_manifest_or_validation()

    request_body = execute_pipeline_to_agent_request(
        request,
        drive_client=InvalidDriveClient(),
        bigquery_client=bigquery_client,
        trocco_client=FakeTroccoClient(),
    )
    payload = request_body["input"]["payload"]

    assert bigquery_client.load_called is False
    assert payload["manifest_diff"]["records"][0]["detected_action"] == "invalid"
    assert payload["validation"]["status"] == "failed"
    assert payload["staging"]["status"] == "not_started"


def test_execute_pipeline_skips_bigquery_for_duplicate_only_manifest():
    bigquery_client = FakeBigQueryClient()
    request = _request_without_manifest_or_validation()
    request["manifest"] = {
        "existing_rows": [
            {
                "provider": "apple",
                "sales_yyyymm": "202606",
                "file_id": "apple_file_001",
                "file_name": "202606_ICE納品.xlsx",
                "md5_checksum": "md5-apple-001",
                "delivery_type": "ICE納品",
                "is_active_after": True,
            }
        ]
    }

    request_body = execute_pipeline_to_agent_request(
        request,
        drive_client=FakeDriveClient(),
        bigquery_client=bigquery_client,
        trocco_client=FakeTroccoClient(),
    )
    payload = request_body["input"]["payload"]

    assert bigquery_client.load_called is False
    assert payload["manifest_diff"]["diff_summary"]["duplicate_count"] == 1
    assert payload["staging"]["status"] == "not_started"
    assert payload["trocco"]["status"] == "not_triggered"


def test_execute_pipeline_can_disable_manifest_write():
    bigquery_client = FakeBigQueryClient()
    request = _request_without_manifest_or_validation()
    request["manifest"] = {"write_enabled": False}

    request_body = execute_pipeline_to_agent_request(
        request,
        drive_client=FakeDriveClient(),
        bigquery_client=bigquery_client,
        trocco_client=FakeTroccoClient(),
    )
    payload = request_body["input"]["payload"]

    assert bigquery_client.written_manifest_rows == []
    assert payload["manifest_diff"]["write_result"]["status"] == "skipped"


def test_execute_pipeline_maps_landing_upload_failure_to_staging_failed():
    bigquery_client = FakeBigQueryClient()
    request = _request_without_manifest_or_validation()
    request["landing"] = {"bucket": "sales-landing", "prefix": "drive-import"}

    request_body = execute_pipeline_to_agent_request(
        request,
        drive_client=FakeDriveClient(),
        storage_client=FailingStorageClient(),
        bigquery_client=bigquery_client,
        trocco_client=FakeTroccoClient(),
    )
    payload = request_body["input"]["payload"]

    assert bigquery_client.load_called is False
    assert payload["staging"]["status"] == "failed"
    assert payload["staging"]["landing_uploads"][0]["status"] == "failed"
    assert payload["trocco"]["status"] == "not_triggered"

from src.safe_execute import execute_safe_mode


RUN_CONTEXT = {
    "environment": "prod",
    "trigger_source": "manual_cloudshell",
    "run_id": "manual__apple__202605__promotion_only",
    "run_started_at": "2026-07-08T00:00:00Z",
    "run_finished_at": "2026-07-08T00:01:00Z",
    "is_test": False,
    "execution_mode": "promotion_only",
}


class FakeBigQueryClient:
    def __init__(self):
        self.load_called = False
        self.promotion_operations = None
        self.verification_checks = None

    def fetch_manifest_existing_rows(self, *, provider, sales_yyyymm, table):
        raise AssertionError("manifest fetch should not run in promotion_only")

    def write_manifest_rows(self, rows, *, table, run_context=None):
        raise AssertionError("manifest write should not run in promotion_only")

    def run_load_jobs(self, load_jobs):
        self.load_called = True
        raise AssertionError("load jobs should not run in promotion_only")

    def run_promotion(self, operations):
        self.promotion_operations = operations
        return [
            {
                "sales_yyyymm": "202605",
                "status": "success",
                "deleted_row_count": 1596,
                "inserted_row_count": 798,
                "error_message": None,
            }
        ]

    def run_verification(self, checks):
        self.verification_checks = checks
        return [
            {
                "name": "production_row_count_matches_staging_202605",
                "status": "passed",
                "expected": True,
                "actual": True,
            }
        ]


class FakeTroccoClient:
    def __init__(self):
        self.calls = []

    def trigger_workflow(self, *, workflow_id, payload):
        self.calls.append({"workflow_id": workflow_id, "payload": payload})
        return {"status_code": 200, "body": {"job_id": "trocco-job"}}


def test_promotion_only_runs_only_promotion_and_verification():
    bigquery_client = FakeBigQueryClient()

    result = execute_safe_mode(
        {
            "provider": "apple",
            "sales_yyyymm": ["202605"],
            "run_context": RUN_CONTEXT,
            "bigquery": {
                "promotion_operations": [
                    {
                        "sales_yyyymm": "202605",
                        "delete_sql": "DELETE FROM prod WHERE sales_yyyymm = '202605'",
                        "insert_sql": "INSERT INTO prod SELECT * FROM stg WHERE sales_yyyymm = '202605'",
                    }
                ],
                "verification_checks": [
                    {
                        "name": "production_row_count_matches_staging_202605",
                        "sql": "SELECT TRUE",
                        "expected": True,
                    }
                ],
            },
            "execution_mode": "promotion_only",
        },
        bigquery_client=bigquery_client,
    )

    assert bigquery_client.load_called is False
    assert bigquery_client.promotion_operations[0]["sales_yyyymm"] == "202605"
    assert bigquery_client.verification_checks[0]["expected"] is True
    assert result["execution_results"]["bigquery"]["load_jobs"] == []
    assert result["execution_results"]["bigquery"]["promotion_operations"][0]["inserted_row_count"] == 798
    assert result["execution_results"]["manifest"]["write_result"]["status"] == "skipped"


def test_trocco_only_runs_trocco_without_bigquery():
    trocco_client = FakeTroccoClient()

    result = execute_safe_mode(
        {
            "provider": "googleplay",
            "sales_yyyymm": ["202605"],
            "run_context": {**RUN_CONTEXT, "execution_mode": "trocco_only"},
            "execution_mode": "trocco_only",
            "trocco_payload": {"datamart_definition_ids": [93283, 93281, 93284]},
        },
        trocco_client=trocco_client,
    )

    assert trocco_client.calls == [
        {
            "workflow_id": 44652,
            "payload": {"datamart_definition_ids": [93283, 93281, 93284]},
        }
    ]
    assert result["execution_results"]["bigquery"]["load_jobs"] == []
    assert result["execution_results"]["bigquery"]["promotion_operations"] == []
    assert result["execution_results"]["trocco"]["response"]["body"]["job_id"] == "trocco-job"

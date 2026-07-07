import json

from src.pipeline_clients import GoogleBigQueryClient, TroccoApiClient


class FakeQueryJob:
    def __init__(self, *, job_id, affected_rows):
        self.job_id = job_id
        self.num_dml_affected_rows = affected_rows

    def result(self):
        return self


class FakeBigQueryClient:
    def __init__(self):
        self.jobs = [
            FakeQueryJob(job_id="delete-job", affected_rows=4),
            FakeQueryJob(job_id="insert-job", affected_rows=9),
        ]

    def query(self, sql):
        return self.jobs.pop(0)


class FakeResponse:
    def __init__(self, *, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self):
        self.requests = []

    def post(self, url, *, json, headers, timeout):
        self.requests.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(status_code=201, body={"id": f"trocco-job-{len(self.requests)}"})


def test_run_promotion_returns_json_serializable_success_result():
    client = GoogleBigQueryClient(client=FakeBigQueryClient())

    result = client.run_promotion(
        [
            {
                "sales_yyyymm": "202605",
                "delete_sql": "DELETE FROM table WHERE sales_yyyymm = '202605'",
                "insert_sql": "INSERT INTO table SELECT * FROM staging",
            }
        ]
    )

    assert result == [
        {
            "sales_yyyymm": "202605",
            "status": "success",
            "delete_job_id": "delete-job",
            "insert_job_id": "insert-job",
            "deleted_row_count": 4,
            "inserted_row_count": 9,
            "error_message": None,
        }
    ]
    json.dumps(result)


def test_trocco_api_client_triggers_datamart_jobs_in_order():
    session = FakeSession()
    client = TroccoApiClient(base_url="https://trocco.example", api_key="secret", session=session)

    result = client.trigger_workflow(
        workflow_id=44652,
        payload={
            "datamart_definition_ids": [93283, 93281, 93284],
            "context_time": "2026-07-07T18:45:00+09:00",
            "custom_variables": [{"name": "sales_yyyymm", "value": "202605"}],
        },
    )

    assert result == {
        "status_code": 200,
        "body": {
            "workflow_id": 44652,
            "job_id": "trocco-job-3",
            "datamart_jobs": [
                {
                    "datamart_definition_id": 93283,
                    "status_code": 201,
                    "body": {"id": "trocco-job-1"},
                    "job_id": "trocco-job-1",
                },
                {
                    "datamart_definition_id": 93281,
                    "status_code": 201,
                    "body": {"id": "trocco-job-2"},
                    "job_id": "trocco-job-2",
                },
                {
                    "datamart_definition_id": 93284,
                    "status_code": 201,
                    "body": {"id": "trocco-job-3"},
                    "job_id": "trocco-job-3",
                },
            ],
        },
    }
    assert [request["url"] for request in session.requests] == [
        "https://trocco.example/api/datamart_jobs",
        "https://trocco.example/api/datamart_jobs",
        "https://trocco.example/api/datamart_jobs",
    ]
    assert [request["json"]["datamart_definition_id"] for request in session.requests] == [93283, 93281, 93284]
    assert session.requests[0]["json"]["custom_variables"] == [{"name": "sales_yyyymm", "value": "202605"}]
    json.dumps(result)

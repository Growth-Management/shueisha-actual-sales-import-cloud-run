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
    status_code = 201
    text = '{"job_id":"trocco-job"}'

    def json(self):
        return {"job_id": "trocco-job"}


class FakeSession:
    def __init__(self):
        self.request = None

    def post(self, url, *, json, headers, timeout):
        self.request = {
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        }
        return FakeResponse()


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


def test_trocco_api_client_returns_json_serializable_response():
    session = FakeSession()
    client = TroccoApiClient(base_url="https://trocco.example", api_key="secret", session=session)

    result = client.trigger_workflow(workflow_id=44652, payload={"provider": "googleplay"})

    assert result == {"status_code": 201, "body": {"job_id": "trocco-job"}}
    assert session.request["url"] == "https://trocco.example/api/workflows/44652/runs"
    assert session.request["json"] == {"provider": "googleplay"}
    json.dumps(result)

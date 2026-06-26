# shueisha-actual-sales-import-cloud-run

Cloud Run repository for the Shueisha Apple / Google Play actual sales import pipeline.

## Current State

This repository currently contains the payload v1.0 integration scaffold. The next step is to add the actual Cloud Run service code and wire the run result assembly to the payload builder.

Remote:

```text
https://github.com/Growth-Management/shueisha-actual-sales-import-cloud-run.git
```

## Included Integration Assets

Payload v1.0 integration files are staged under:

```text
integration/payload_v1/
```

Key files:

- `payload_builder.py`
- `payload-schema-v1.json`
- `provider-mapping-v1.md`
- `cloud_run_integration_example.py`
- `test_payload_builder.py`
- `check_sample_payloads.py`
- `INTEGRATION_CHECKLIST.md`

## Next implementation step

The current Cloud Run entrypoint is `src/main.py`.

Available endpoints:

- `GET /readiness`
- `POST /agent-request`
- `POST /run-result/agent-request`
- `POST /execution-results/agent-request`
- `POST /execute/agent-request`

`POST /agent-request` accepts either a payload object directly or a wrapper object with `payload`. By default it validates and wraps the payload as the agent API request body. Set `finalize_payload: true` to have the service calculate TROCCO trigger fields before wrapping.

`POST /run-result/agent-request` accepts Cloud Run internal run result fields, builds payload v1.0, and returns the agent API request body.

Adapter helpers for converting step outputs into `run_result` sections are in `src/run_result_adapters.py`.

Execution result adapters for raw Drive / BigQuery / TROCCO / webhook responses are in `src/execution_result_adapters.py`.

`POST /execution-results/agent-request` accepts actual execution-result-shaped values from Drive polling, BigQuery load / promotion / verification, and TROCCO trigger execution. It connects those raw results through:

1. `execution_result_adapters`
2. `run_result_adapters`
3. `build_payload_from_run_result`
4. `build_agent_request`

Expected top-level shape:

```json
{
  "provider": "apple",
  "sales_yyyymm": ["202606"],
  "run_context": {
    "environment": "prod",
    "trigger_source": "cloud_run_hourly",
    "run_id": "2026-06-26T10:00:00Z__apple__001",
    "run_started_at": "2026-06-26T10:00:00Z",
    "run_finished_at": "2026-06-26T10:03:42Z",
    "is_test": false
  },
  "execution_results": {
    "drive": {
      "files": [],
      "detected_actions_by_file_id": {}
    },
    "manifest": {
      "rows": []
    },
    "validation": {
      "results": []
    },
    "bigquery": {
      "load_jobs": [],
      "promotion_operations": [],
      "verification_checks": []
    },
    "trocco": {
      "response": {
        "status_code": 201,
        "body": {
          "job_id": "trocco_job_id"
        }
      }
    }
  }
}
```

`POST /execute/agent-request` runs the pipeline clients first, then builds the same agent API request. It performs:

1. Drive folder polling
2. BigQuery load jobs
3. BigQuery production promotion jobs
4. BigQuery verification checks
5. TROCCO workflow trigger only when payload v1.0 preconditions pass

The request must include manifest rows and validation results produced by the surrounding import logic, plus BigQuery job definitions:

```json
{
  "provider": "apple",
  "sales_yyyymm": ["202606"],
  "run_context": {
    "environment": "prod",
    "trigger_source": "cloud_run_hourly",
    "run_id": "2026-06-26T10:00:00Z__apple__001",
    "run_started_at": "2026-06-26T10:00:00Z",
    "run_finished_at": null,
    "is_test": false
  },
  "manifest": {
    "rows": []
  },
  "validation": {
    "results": []
  },
  "bigquery": {
    "load_jobs": [],
    "promotion_operations": [],
    "verification_checks": []
  },
  "trocco_payload": {}
}
```

## Local Run

```bash
pip install -r requirements.txt
gunicorn --bind :8080 --workers 1 --threads 8 --timeout 0 src.main:app
```

## Local Checks

From `integration/payload_v1/`:

```bash
python - <<'PY'
import test_payload_builder as t

t.test_success_payload_triggers_trocco()
t.test_staging_failure_does_not_trigger_trocco()
t.test_duplicate_only_notification()
t.test_provider_delivery_type_mapping()
print("payload_builder tests passed")
PY
```

To validate sample payloads, set `PAYLOAD_SAMPLE_DIR` when sample JSON files are outside this repository:

```bash
PAYLOAD_SAMPLE_DIR=/workspace/agent_files/docs python check_sample_payloads.py
```

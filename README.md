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
2. Manifest diff generation
3. Validation result generation
4. Drive file upload to GCS landing
5. BigQuery load jobs
6. BigQuery production promotion jobs
7. BigQuery verification checks
8. TROCCO workflow trigger only when payload v1.0 preconditions pass

The request can include prebuilt `manifest.rows` and `validation.results`. If omitted, Cloud Run builds them from Drive file metadata and optional `manifest.existing_rows`.

BigQuery load / promotion / verification is skipped when validation fails or when the manifest diff has no `new` or `revised` files.

When `manifest.existing_rows` is omitted, Cloud Run fetches active rows from `ice-sh.ice_sh_process.drive_sales_import_manifest`. Generated manifest rows are written back after execution unless `manifest.write_enabled` is `false`.

When `landing.bucket` is provided, Cloud Run uploads `new` / `revised` Drive files to GCS and injects the generated `gs://...` URI into matching BigQuery load jobs.
If a GCS landing upload fails, staging is marked as failed and promotion / verification / TROCCO are skipped.

BigQuery settings can be provided explicitly, but Cloud Run also generates defaults from `provider` and `sales_yyyymm`:

- `load_job_template` defaults to CSV load settings and the provider staging table.
- `load_jobs` are generated from successful GCS landing uploads and merged with `load_job_template`.
- `promotion_operations` default to month-level `DELETE` from production followed by `INSERT ... SELECT` from staging.
- `verification_checks` default to month-level production/staging row-count equality checks.
- promotion and verification run only after at least one load job exists and all load jobs succeed.

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
    "table": "ice-sh.ice_sh_process.drive_sales_import_manifest",
    "fetch_existing_rows": true,
    "write_enabled": true
  },
  "landing": {
    "bucket": "your-gcs-landing-bucket",
    "prefix": "drive-sales-import"
  },
  "bigquery": {
    "load_job_template": {
      "job_config": {
        "source_format": "CSV",
        "autodetect": true,
        "skip_leading_rows": 1,
        "write_disposition": "WRITE_APPEND",
        "field_delimiter": ",",
        "allow_quoted_newlines": true,
        "encoding": "UTF-8"
      }
    },
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

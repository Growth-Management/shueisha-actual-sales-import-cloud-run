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

`POST /agent-request` accepts either a payload object directly or a wrapper object with `payload`. By default it validates and wraps the payload as the agent API request body. Set `finalize_payload: true` to have the service calculate TROCCO trigger fields before wrapping.

`POST /run-result/agent-request` accepts Cloud Run internal run result fields, builds payload v1.0, and returns the agent API request body.

Adapter helpers for converting step outputs into `run_result` sections are in `src/run_result_adapters.py`.

The next implementation step is to replace stubbed adapter inputs with actual Drive / BigQuery / TROCCO execution results:

1. `build_base_payload`
2. `finalize_payload`
3. `build_agent_request`

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

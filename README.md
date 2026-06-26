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

Add the actual Cloud Run service code, then wire the run result assembly to:

1. `build_base_payload`
2. `finalize_payload`
3. `build_agent_request`

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

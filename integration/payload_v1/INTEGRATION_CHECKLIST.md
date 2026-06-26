# Payload v1.0 Cloud Run integration checklist

## Copy files

Copy these files into the Cloud Run repository module that builds the agent request:

- `payload_builder.py`
- `payload-schema-v1.json`
- `provider-mapping-v1.md`
- `cloud_run_integration_example.py`
- `test_payload_builder.py`
- `check_sample_payloads.py`

## Wire the pipeline

Use this sequence in Cloud Run:

1. Build the base payload with `build_base_payload`.
2. Add actual Drive detection and manifest diff results.
3. Add actual validation results.
4. Add actual staging load results.
5. Add actual production promotion results.
6. Add actual production verification results.
7. Call `finalize_payload`.
8. Add webhook notification result if Cloud Run sends Slack notifications.
9. Call `build_agent_request`.
10. Send the resulting request body to the agent API.

## Required checks

- Apple normal success triggers TROCCO.
- Google Play normal success triggers TROCCO.
- No new or revised files does not trigger TROCCO.
- Duplicate-only detection does not trigger TROCCO.
- Format error does not trigger staging, promotion, verification, or TROCCO.
- Staging failure does not trigger promotion, verification, or TROCCO.
- Promotion failure does not trigger verification or TROCCO.
- Verification failure does not trigger TROCCO.
- TROCCO API failure returns `trocco.status = trigger_failed`.

## Expected command checks

If `pytest` is available:

```bash
python -m pytest -q
```

Without `pytest`:

```bash
python - <<'PY'
import test_payload_builder as t

t.test_success_payload_triggers_trocco()
t.test_staging_failure_does_not_trigger_trocco()
t.test_duplicate_only_notification()
t.test_provider_delivery_type_mapping()
print("payload_builder tests passed")
PY

python check_sample_payloads.py
```

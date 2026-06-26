# shueisha-actual-sales-import-cloud-run

Cloud Run repository staging for the Drive sales import payload v1.0 integration.

## Current state

The GitHub repository `Growth-Management/shueisha-actual-sales-import-cloud-run` is currently empty, so this local repository was initialized as the placement target.

Remote:

```text
https://github.com/Growth-Management/shueisha-actual-sales-import-cloud-run.git
```

## Included integration assets

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

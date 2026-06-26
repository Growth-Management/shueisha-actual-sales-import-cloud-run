from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from flask import Flask, jsonify, request


REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_V1_DIR = REPO_ROOT / "integration" / "payload_v1"
if str(PAYLOAD_V1_DIR) not in sys.path:
    sys.path.insert(0, str(PAYLOAD_V1_DIR))

from payload_builder import (  # noqa: E402
    build_agent_request,
    build_webhook_notification,
    finalize_payload,
    validate_payload,
)


app = Flask(__name__)


def _error_response(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def _bool_from_body(body: dict[str, Any], key: str, default: bool = False) -> bool:
    value = body.get(key, default)
    if isinstance(value, bool):
        return value
    return default


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.post("/agent-request")
def agent_request():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error_response("request body must be a JSON object")

    payload = body.get("payload", body)
    if not isinstance(payload, dict):
        return _error_response("payload must be a JSON object")

    try:
        if _bool_from_body(body, "finalize_payload", False):
            payload = finalize_payload(
                payload,
                trocco_api_called=_bool_from_body(body, "trocco_api_called", False),
                trocco_api_succeeded=_bool_from_body(body, "trocco_api_succeeded", False),
                trocco_job_id=body.get("trocco_job_id"),
                trocco_error_message=body.get("trocco_error_message"),
            )
        else:
            validate_payload(payload)

        if _bool_from_body(body, "include_webhook_notification", False) and "webhook_notification" not in payload:
            payload["webhook_notification"] = build_webhook_notification(
                payload,
                status=body.get("webhook_status", "not_sent"),
                sent_at=body.get("webhook_sent_at"),
                error_message=body.get("webhook_error_message"),
            )

        request_body = build_agent_request(
            payload,
            requested_output=body.get("requested_output", "run_judgment"),
            include_notification_draft=_bool_from_body(body, "include_notification_draft", True),
            include_failure_analysis=_bool_from_body(body, "include_failure_analysis", False),
        )
    except ValueError as exc:
        return _error_response(str(exc))

    return jsonify(request_body)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from flask import Flask, jsonify, request


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
PAYLOAD_V1_DIR = REPO_ROOT / "integration" / "payload_v1"
for import_dir in (SRC_DIR, PAYLOAD_V1_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))

from payload_builder import (  # noqa: E402
    build_agent_request,
    build_webhook_notification,
    finalize_payload,
    validate_payload,
)
from execution_result_connector import build_agent_request_from_execution_results  # noqa: E402
from pipeline_defaults import (  # noqa: E402
    apply_execution_defaults,
    execution_mode_from_request,
    has_landing_bucket,
)
from pipeline_executor import execute_pipeline, execute_pipeline_to_agent_request  # noqa: E402
from run_result_mapper import build_payload_from_run_result  # noqa: E402


app = Flask(__name__)


def _error_response(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def _bool_from_body(body: dict[str, Any], key: str, default: bool = False) -> bool:
    value = body.get(key, default)
    if isinstance(value, bool):
        return value
    return default


def _with_execution_mode(request_body: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    payload = request_body.get("input", {}).get("payload")
    if isinstance(payload, dict) and "execution_mode" not in payload:
        payload["execution_mode"] = execution_mode_from_request(source)
    return request_body


def _prepare_execution_body(body: dict[str, Any], *, require_landing_bucket: bool = False) -> dict[str, Any]:
    execution_body = apply_execution_defaults(body)
    if require_landing_bucket and not has_landing_bucket(execution_body):
        raise ValueError("landing.bucket or LANDING_BUCKET environment variable is required for /execute")
    return execution_body


@app.get("/")
def index():
    return jsonify(
        {
            "status": "ok",
            "service": "shueisha-actual-sales-import",
            "readiness": "/readiness",
            "execute": "/execute",
            "execute_agent_request": "/execute/agent-request",
        }
    )


@app.get("/readiness")
def readiness():
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
        request_body = _with_execution_mode(request_body, body)
    except ValueError as exc:
        return _error_response(str(exc))

    return jsonify(request_body)


@app.post("/run-result/agent-request")
def run_result_agent_request():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error_response("request body must be a JSON object")

    run_result = body.get("run_result", body)
    if not isinstance(run_result, dict):
        return _error_response("run_result must be a JSON object")

    try:
        payload = build_payload_from_run_result(run_result)
        request_body = build_agent_request(
            payload,
            requested_output=body.get("requested_output", "run_judgment"),
            include_notification_draft=_bool_from_body(body, "include_notification_draft", True),
            include_failure_analysis=_bool_from_body(body, "include_failure_analysis", False),
        )
        request_body = _with_execution_mode(request_body, body)
    except ValueError as exc:
        return _error_response(str(exc))

    return jsonify(request_body)


@app.post("/execution-results/agent-request")
def execution_results_agent_request():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error_response("request body must be a JSON object")

    execution_result = body.get("execution_result", body)
    if not isinstance(execution_result, dict):
        return _error_response("execution_result must be a JSON object")

    try:
        request_body = build_agent_request_from_execution_results(
            execution_result,
            requested_output=body.get("requested_output", "run_judgment"),
            include_notification_draft=_bool_from_body(body, "include_notification_draft", True),
            include_failure_analysis=_bool_from_body(body, "include_failure_analysis", False),
        )
        request_body = _with_execution_mode(request_body, body)
    except ValueError as exc:
        return _error_response(str(exc))

    return jsonify(request_body)


@app.post("/execute")
def execute():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error_response("request body must be a JSON object")

    try:
        execution_body = _prepare_execution_body(body, require_landing_bucket=True)
        execution_result = execute_pipeline(execution_body)
    except ValueError as exc:
        return _error_response(str(exc))

    return jsonify(execution_result)


@app.post("/execute/agent-request")
def execute_agent_request():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error_response("request body must be a JSON object")

    try:
        execution_body = _prepare_execution_body(body)
        request_body = execute_pipeline_to_agent_request(execution_body)
        request_body = _with_execution_mode(request_body, execution_body)
    except ValueError as exc:
        return _error_response(str(exc))

    return jsonify(request_body)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

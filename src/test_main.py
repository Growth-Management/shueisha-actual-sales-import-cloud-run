import src.main as main


app = main.app


def test_index_returns_service_status():
    client = app.test_client()

    response = client.get("/")

    body = response.get_json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["execute"] == "/execute"


def test_readiness_returns_ok():
    client = app.test_client()

    response = client.get("/readiness")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_execute_agent_request_includes_execution_mode(monkeypatch):
    def fake_execute_pipeline_to_agent_request(body):
        assert body["execution_mode"] == "staging_load_only"
        return {"input": {"payload": {"provider": "googleplay"}}}

    monkeypatch.setattr(main, "execute_pipeline_to_agent_request", fake_execute_pipeline_to_agent_request)
    client = app.test_client()

    response = client.post(
        "/execute/agent-request",
        json={"execution_mode": "staging_load_only"},
    )

    assert response.status_code == 200
    assert response.get_json()["input"]["payload"]["execution_mode"] == "staging_load_only"


def test_execute_agent_request_uses_run_context_execution_mode(monkeypatch):
    def fake_execute_pipeline_to_agent_request(body):
        assert body["execution_mode"] == "staging_load_only"
        return {"input": {"payload": {"provider": "googleplay"}}}

    monkeypatch.setattr(main, "execute_pipeline_to_agent_request", fake_execute_pipeline_to_agent_request)
    client = app.test_client()

    response = client.post(
        "/execute/agent-request",
        json={"run_context": {"execution_mode": "staging_load_only"}},
    )

    assert response.status_code == 200
    assert response.get_json()["input"]["payload"]["execution_mode"] == "staging_load_only"


def test_execute_requires_landing_bucket(monkeypatch):
    monkeypatch.delenv("LANDING_BUCKET", raising=False)
    client = app.test_client()

    response = client.post(
        "/execute",
        json={
            "run_context": {"execution_mode": "staging_load_only"},
            "provider": "googleplay",
            "sales_yyyymm": ["202605"],
        },
    )

    assert response.status_code == 400
    assert "landing.bucket" in response.get_json()["error"]


def test_execute_applies_landing_bucket_env(monkeypatch):
    def fake_execute_pipeline(body):
        assert body["execution_mode"] == "staging_load_only"
        assert body["landing"] == {
            "bucket": "ice-sh-drive-sales-import-landing",
            "prefix": "landing/drive-sales-import",
        }
        return {"provider": body["provider"], "execution_results": {}}

    monkeypatch.setenv("LANDING_BUCKET", "ice-sh-drive-sales-import-landing")
    monkeypatch.delenv("LANDING_PREFIX", raising=False)
    monkeypatch.setattr(main, "execute_pipeline", fake_execute_pipeline)
    client = app.test_client()

    response = client.post(
        "/execute",
        json={
            "run_context": {"execution_mode": "staging_load_only"},
            "provider": "googleplay",
            "sales_yyyymm": ["202605"],
        },
    )

    assert response.status_code == 200
    assert response.get_json()["provider"] == "googleplay"


def test_execute_allows_trocco_only_without_landing_bucket(monkeypatch):
    def fake_execute_safe_mode(body):
        assert body["execution_mode"] == "trocco_only"
        assert "landing" not in body or "bucket" not in body["landing"]
        return {"provider": body["provider"], "execution_results": {"trocco": {}}}

    monkeypatch.delenv("LANDING_BUCKET", raising=False)
    monkeypatch.setattr(main, "execute_safe_mode", fake_execute_safe_mode)
    client = app.test_client()

    response = client.post(
        "/execute",
        json={
            "run_context": {"execution_mode": "trocco_only"},
            "provider": "googleplay",
            "sales_yyyymm": ["202605"],
        },
    )

    assert response.status_code == 200
    assert response.get_json()["provider"] == "googleplay"

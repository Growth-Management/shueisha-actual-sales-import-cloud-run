import src.main as main


app = main.app


def test_index_returns_service_status():
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


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

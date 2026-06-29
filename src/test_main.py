from src.main import app


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

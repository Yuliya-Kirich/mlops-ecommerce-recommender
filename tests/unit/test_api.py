import pytest
from fastapi.testclient import TestClient

from src.api import main as api


@pytest.fixture
def client():
    # Не запускаем lifespan: тесты не обращаются к S3.
    return TestClient(api.app)


@pytest.fixture(autouse=True)
def reset_model(monkeypatch):
    # Каждый тест начинается без загруженной модели.
    monkeypatch.setattr(api, "model", None)


def valid_payload():
    return {
        "views": 10,
        "purchases": 2,
        "ctr": 0.2,
        "hour": 14,
        "weekday": 3,
        "categoryid": 100,
        "available": 1,
    }


def test_health_without_model(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "model_loaded": False,
    }


def test_health_with_model(client, monkeypatch):
    monkeypatch.setattr(api, "model", object())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_loaded": True,
    }


def test_predict_without_model(client):
    response = client.post(
        "/predict_purchase",
        json=valid_payload(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Модель не загружена"


@pytest.mark.parametrize(
    "field,value",
    [
        ("views", -1),
        ("purchases", -1),
        ("ctr", -0.1),
        ("hour", 24),
        ("weekday", 7),
        ("available", 2),
    ],
)
def test_invalid_input(client, field, value):
    payload = valid_payload()
    payload[field] = value

    response = client.post(
        "/predict_purchase",
        json=payload,
    )

    assert response.status_code == 422


def test_predict_with_mock_model(client, monkeypatch):
    class MockModel:
        def predict_proba(self, features):
            assert list(features.columns) == api.FEATURES
            assert len(features) == 1
            return __import__("numpy").array([[0.25, 0.75]])

    monkeypatch.setattr(api, "model", MockModel())
    monkeypatch.setenv("MODEL_VERSION", "test-version")

    response = client.post(
        "/predict_purchase",
        json=valid_payload(),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["purchase_probability"] == pytest.approx(0.75)
    assert result["model_version"] == "test-version"

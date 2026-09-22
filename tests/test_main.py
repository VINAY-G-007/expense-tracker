"""Tests for the Expense Tracker API.  Run from the project folder with:  pytest"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

import main


@pytest.fixture()
def client():
    # Every test starts with an empty table in the temporary test database.
    SQLModel.metadata.drop_all(main.engine)
    SQLModel.metadata.create_all(main.engine)
    with TestClient(main.app) as test_client:
        yield test_client


def add(client, amount=250.0, category="Food", description="Lunch"):
    """Create an expense through the API and return it."""
    payload = {"amount": amount, "category": category, "description": description}
    response = client.post("/expenses", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_tests_use_a_temporary_database():
    assert "test.db" in str(main.engine.url)


def test_home_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Expense Tracker" in response.text


def test_health_check(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_expense(client):
    expense = add(client, 250.5, "Food", "Lunch")
    assert expense == {"id": 1, "amount": 250.5, "category": "Food", "description": "Lunch"}


def test_text_is_trimmed_and_description_is_optional(client):
    response = client.post("/expenses", json={"amount": 99, "category": "  Travel  "})
    assert response.status_code == 201
    assert response.json()["category"] == "Travel"
    assert response.json()["description"] == ""


def test_list_expenses_oldest_first(client):
    add(client, 100, "Food")
    add(client, 50, "Travel")
    expenses = client.get("/expenses").json()
    assert [e["category"] for e in expenses] == ["Food", "Travel"]


def test_filter_by_category(client):
    add(client, 100, "Food")
    add(client, 50, "Travel")
    add(client, 20, "Food")
    expenses = client.get("/expenses", params={"category": "Food"}).json()
    assert [e["amount"] for e in expenses] == [100, 20]


def test_get_one_expense(client):
    created = add(client)
    response = client.get(f"/expenses/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_update_expense(client):
    created = add(client, 250, "Food", "Lunch")
    changes = {"amount": 300, "category": "Food", "description": "Dinner"}
    response = client.put(f"/expenses/{created['id']}", json=changes)
    assert response.status_code == 200
    assert response.json() == {"id": created["id"], **changes}
    assert client.get(f"/expenses/{created['id']}").json()["description"] == "Dinner"


def test_delete_expense(client):
    created = add(client)
    response = client.delete(f"/expenses/{created['id']}")
    assert response.status_code == 200
    assert response.json() == {"deleted": created["id"]}
    assert client.get(f"/expenses/{created['id']}").status_code == 404
    assert client.get("/expenses").json() == []


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_expense_returns_404(client, method):
    kwargs = {"json": {"amount": 1, "category": "Food"}} if method == "put" else {}
    response = client.request(method.upper(), "/expenses/999", **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "expense not found"}


@pytest.mark.parametrize("payload", [
    {"amount": 0, "category": "Food"},
    {"amount": -50, "category": "Food"},
    {"amount": "abc", "category": "Food"},
    {"amount": 20_000_000, "category": "Food"},
    {"amount": 10, "category": ""},
    {"amount": 10, "category": "   "},
    {"amount": 10, "category": "x" * 51},
    {"amount": 10, "category": "Food", "description": "x" * 201},
    {"category": "Food"},
    {"amount": 10},
])
def test_invalid_expenses_are_rejected(client, payload):
    response = client.post("/expenses", json=payload)
    assert response.status_code == 422
    assert client.get("/expenses").json() == []


def test_invalid_update_is_rejected(client):
    created = add(client)
    response = client.put(f"/expenses/{created['id']}", json={"amount": -1, "category": "Food"})
    assert response.status_code == 422
    assert client.get(f"/expenses/{created['id']}").json() == created


def test_summary_with_no_expenses(client):
    assert client.get("/expenses/summary").json() == {"total": 0, "count": 0, "by_category": []}


def test_summary_totals_by_category(client):
    add(client, 100.25, "Food")
    add(client, 500, "Rent")
    add(client, 49.75, "Food")
    summary = client.get("/expenses/summary").json()
    assert summary["total"] == 650
    assert summary["count"] == 3
    assert summary["by_category"] == [
        {"category": "Rent", "total": 500, "count": 1},
        {"category": "Food", "total": 150, "count": 2},
    ]

"""Customer search and purchase history contract (additive APIs)."""

from conftest import login, post


def test_customer_lookup_requires_login_and_rejects_warehouse(client):
    assert client.get("/api/customers/lookup?q=anything").status_code == 401
    login(client, "warehouse")
    assert client.get("/api/customers/lookup?q=anything").status_code == 403


def test_customer_lookup_matches_name_and_tax_id_and_paginates(seeded, client):
    token, _pid, cid = seeded
    assert (
        post(
            client,
            token,
            "/customers",
            {"name": "Another buyer", "address": "Synthetic", "tax_id": "1234567890123"},
        ).status_code
        == 201
    )
    assert [c["id"] for c in client.get("/api/customers/lookup?q=synthetic").json["items"]] == [cid]
    assert [c["name"] for c in client.get("/api/customers/lookup?q=123456").json["items"]] == ["Another buyer"]
    result = client.get("/api/customers/lookup?limit=1").json
    assert len(result["items"]) == 1
    assert result["next_after"] is not None
    next_page = client.get(f"/api/customers/lookup?limit=1&after={result['next_after']}").json
    assert next_page["items"][0]["id"] != result["items"][0]["id"]


def test_customer_lookup_rejects_invalid_filters(seeded, client):
    assert client.get("/api/customers/lookup?limit=0").status_code == 400
    assert client.get("/api/customers/lookup?limit=101").status_code == 400
    assert client.get("/api/customers/lookup?after=abc").status_code == 400
    assert client.get("/api/customers/lookup?q=" + ("x" * 101)).status_code == 400


def test_customer_history_shows_sales_and_outstanding(seeded, client):
    token, pid, cid = seeded
    sale = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 2}]})
    sid = sale.json["id"]
    assert (
        post(
            client, token, f"/sales/{sid}/payments", {"amount": "100.00", "reference": "history-partial-001"}
        ).status_code
        == 201
    )
    result = client.get(f"/api/customers/{cid}/history")
    assert result.status_code == 200
    assert result.json["customer"]["id"] == cid
    assert result.json["summary"]["total_sales"] == "214.00"
    assert result.json["summary"]["total_paid"] == "100.00"
    assert result.json["summary"]["outstanding"] == "114.00"
    assert result.json["items"][0]["id"] == sid
    assert result.json["items"][0]["balance"] == "114.00"
    assert client.get("/api/customers/99999/history").status_code == 404


def test_customer_history_restricts_warehouse(client):
    login(client, "warehouse")
    assert client.get("/api/customers/1/history").status_code == 403

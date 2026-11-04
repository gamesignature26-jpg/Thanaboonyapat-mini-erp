from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import login, post

from erp.models import Payment, Product, Sale, db


def concurrent_requests(app, path, payloads):
    clients = [app.test_client(), app.test_client()]
    tokens = [login(client) for client in clients]
    barrier = Barrier(2)

    def send(index):
        barrier.wait(timeout=10)
        return post(clients[index], tokens[index], path, payloads[index]).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        return sorted(pool.map(send, (0, 1)))


def test_postgres_prevents_overselling_and_overpayment(app, client, seeded):
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        pytest.skip("Row locks require PostgreSQL")
    _token, pid, cid = seeded
    payload = {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 7}]}
    assert concurrent_requests(app, "/sales", [payload, payload]) == [201, 409]
    with app.app_context():
        assert db.session.get(Product, pid).stock == 3
        sale = db.session.scalar(db.select(Sale))
        sid = sale.id
    assert concurrent_requests(
        app,
        f"/sales/{sid}/payments",
        [
            {"amount": "500.00", "reference": "parallel-1"},
            {"amount": "500.00", "reference": "parallel-2"},
        ],
    ) == [201, 409]
    with app.app_context():
        assert db.session.get(Sale, sid).paid == 500
        assert len(list(db.session.scalars(db.select(Payment)))) == 1

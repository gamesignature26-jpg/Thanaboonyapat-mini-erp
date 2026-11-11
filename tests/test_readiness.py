"""Readiness is a read-only database probe; liveness stays independent of DB."""

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError

from erp.models import db
from erp.readiness import database_is_ready


def test_database_probe_issues_only_select_one():
    engine = create_engine("sqlite:///:memory:")
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        assert database_is_ready(engine) is True
        assert statements == ["SELECT 1"]
    finally:
        engine.dispose()


def test_readiness_route_responds_200_with_live_database(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    assert client.get("/health").status_code == 200


def test_readiness_route_responds_503_without_database(client, app, monkeypatch):
    def broken_connect():
        raise OperationalError("SELECT 1", {}, RuntimeError("connection refused"))

    with app.app_context():
        with monkeypatch.context() as patch:
            patch.setattr(db.engine, "connect", broken_connect)
            response = client.get("/ready")
        assert response.status_code == 503
        assert response.json == {"status": "unavailable"}
    assert client.get("/health").status_code == 200

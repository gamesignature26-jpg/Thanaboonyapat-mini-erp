"""Pure SQLAlchemy readiness checks; safe to run without the ERP application."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError

SOURCE = Path(__file__).resolve().parents[1] / "erp" / "readiness.py"


def load_probe():
    spec = importlib.util.spec_from_file_location("isolated_readiness", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.database_is_ready


def test_readiness_true_when_database_accepts_query():
    engine = create_engine("sqlite:///:memory:")
    try:
        assert load_probe()(engine) is True
    finally:
        engine.dispose()


def test_readiness_false_when_database_connection_fails(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    def broken_connect():
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(engine, "connect", broken_connect)
    try:
        assert load_probe()(engine) is False
    finally:
        engine.dispose()


def test_readiness_false_when_query_fails(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    original_connect = engine.connect

    class BrokenConnection:
        def __enter__(self):
            self.real_conn = original_connect()
            return self

        def exec_driver_sql(self, statement):
            raise OperationalError(statement, {}, RuntimeError("query failed"))

        def __exit__(self, exc_type, exc_value, exc_tb):
            self.real_conn.close()

    monkeypatch.setattr(engine, "connect", lambda: BrokenConnection())
    try:
        assert load_probe()(engine) is False
    finally:
        engine.dispose()


def test_readiness_handles_os_connection_error(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    def unavailable():
        raise OSError("network unreachable")

    monkeypatch.setattr(engine, "connect", unavailable)
    try:
        assert load_probe()(engine) is False
    finally:
        engine.dispose()


def test_readiness_uses_only_single_read_only_sql_statement():
    engine = create_engine("sqlite:///:memory:")
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        assert load_probe()(engine) is True
        assert statements == ["SELECT 1"]
    finally:
        engine.dispose()


def test_readiness_is_boolean():
    engine = create_engine("sqlite:///:memory:")
    try:
        assert type(load_probe()(engine)) is bool
    finally:
        engine.dispose()

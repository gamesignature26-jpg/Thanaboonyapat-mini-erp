"""Read-only database probe for readiness checks."""

from sqlalchemy.exc import SQLAlchemyError


def database_is_ready(engine):
    """Return whether one read-only database round trip succeeds.

    Intentionally uses an engine connection (not a request's ORM session) to
    avoid mutating, rolling back, or otherwise disturbing business transactions.
    """
    try:
        with engine.connect() as connection:
            return connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    except (SQLAlchemyError, OSError):
        return False

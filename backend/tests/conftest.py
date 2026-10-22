import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.db.session import Base, get_db
import app.models  # noqa: F401  Register complete metadata before test schema creation.
from app.main import app


# Automatically load backend/.env.test if present
_env_test_path = os.path.join(os.path.dirname(__file__), "..", ".env.test")
if os.path.exists(_env_test_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_test_path, override=False)
    except ImportError:
        pass


def _test_database_url() -> URL:
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")
    url = make_url(raw_url)
    db_name = (url.database or "").lower()

    # Reject known development, production, and system database targets
    prohibited_targets = {"testmate_ai", "testmate_dev", "testmate_prod", "postgres", "production"}
    if db_name in prohibited_targets or not (db_name.endswith("_test") or db_name == "testmate_test"):
        raise RuntimeError(
            f"TEST_DATABASE_URL target '{db_name}' is not permitted. "
            "Must be an isolated test database ending in '_test' (e.g. 'testmate_test')."
        )

    # Validate host safety (prevent accidental targeting of remote/production instances)
    host = (url.host or "").lower()
    allowed_hosts = {"localhost", "127.0.0.1", "::1"}
    if host and host not in allowed_hosts and os.getenv("ALLOW_REMOTE_TEST_DB", "").lower() != "true":
        raise RuntimeError(
            f"TEST_DATABASE_URL host '{host}' is not a local loopback address. "
            "Set ALLOW_REMOTE_TEST_DB=true if intentional."
        )

    return url


@pytest.fixture(scope="session")
def test_engine() -> Generator[object, None, None]:
    """Create only the isolated PostgreSQL test schema; never target development data."""

    engine = create_engine(_test_database_url(), pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine: object) -> Generator[Session, None, None]:
    connection = test_engine.connect()  # type: ignore[union-attr]
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

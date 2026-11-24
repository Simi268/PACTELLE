
import os
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base

# Import all models so their tables are registered.
import app.models


TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://pactelle_user:pactelle_dev_password@localhost:5434/pactelle_test_db"
)

test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True
)

TestingSessionLocal = sessionmaker(
    bind=None,
    autoflush=False,
    autocommit=False,
    join_transaction_mode="create_savepoint"
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()

@pytest.fixture
def db_session():
    connection = test_engine.connect()
    transaction = connection.begin()

    session = TestingSessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()

        if transaction.is_active:
            transaction.rollback()

        connection.close()

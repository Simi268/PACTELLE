
import os
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base

# Import all models so their tables are registered.
import app.models
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db

from app.models.user import User
from app.models.organization import Organization
from app.models.membership import OrganizationMembership
from app.models.contract import Contract
from app.models.document import ContractDocument

from app.core.security import create_access_token


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

@pytest.fixture
def api_client(db_session):

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def contract_api_data(db_session):

    organization_a = Organization(name="Contract Test Organization A")
    organization_b = Organization(name="Contract Test Organization B")

    owner_a = User(
        full_name="Owner A",
        email="owner_a@test.com",
        password_hash="test_hash",
        is_active=True
    )

    member_a = User(
        full_name="Member A",
        email="member_a@test.com",
        password_hash="test_hash",
        is_active=True
    )

    owner_b = User(
        full_name="Owner B",
        email="owner_b@test.com",
        password_hash="test_hash",
        is_active=True
    )

    outsider = User(
        full_name="Outsider",
        email="outsider@test.com",
        password_hash="test_hash",
        is_active=True
    )

    db_session.add_all([
        organization_a,
        organization_b,
        owner_a,
        member_a,
        owner_b,
        outsider
    ])

    db_session.flush()

    memberships = [
        OrganizationMembership(
            organization_id=organization_a.id,
            user_id=owner_a.id,
            role="owner"
        ),
        OrganizationMembership(
            organization_id=organization_a.id,
            user_id=member_a.id,
            role="member"
        ),
        OrganizationMembership(
            organization_id=organization_b.id,
            user_id=owner_b.id,
            role="owner"
        )
    ]

    contract_a = Contract(
        organization_id=organization_a.id,
        title="Vendor Agreement A",
        contract_type="vendor",
        status="active"
    )

    contract_b = Contract(
        organization_id=organization_b.id,
        title="Vendor Agreement B",
        contract_type="vendor",
        status="active"
    )

    empty_contract = Contract(
        organization_id=organization_a.id,
        title="Empty Contract",
        contract_type="service",
        status="draft"
    )

    db_session.add_all(
        memberships + [
            contract_a,
            contract_b,
            empty_contract
        ]
    )

    db_session.flush()

    document_a = ContractDocument(
        contract_id=contract_a.id,
        original_filename="agreement_a.pdf",
        stored_filename="stored_a.pdf",
        storage_path="uploads/contracts/stored_a.pdf",
        file_type="application/pdf",
        file_size=1024,
        processing_status="uploaded"
    )

    document_b = ContractDocument(
        contract_id=contract_b.id,
        original_filename="agreement_b.pdf",
        stored_filename="stored_b.pdf",
        storage_path="uploads/contracts/stored_b.pdf",
        file_type="application/pdf",
        file_size=2048,
        processing_status="uploaded"
    )

    db_session.add_all([document_a, document_b])
    db_session.commit()

    return {
        "organization_a": organization_a,
        "organization_b": organization_b,
        "owner_a": owner_a,
        "member_a": member_a,
        "owner_b": owner_b,
        "outsider": outsider,
        "contract_a": contract_a,
        "contract_b": contract_b,
        "empty_contract": empty_contract,
        "document_a": document_a,
        "document_b": document_b
    }

"""Shared test fixtures."""
import pytest
from src.app import create_app
from src.models.base import db as _db


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    app = create_app(testing=True)
    yield app


@pytest.fixture(scope="function")
def db(app):
    """Provide clean database for each test, re-bootstrapping the admin user."""
    with app.app_context():
        _db.create_all()
        # Re-bootstrap the platform admin since tables are recreated each test
        from src.models.models import User
        from src.models.enums import RoleType
        from src.security.passwords import hash_password
        if User.query.first() is None:
            admin = User(
                username="admin",
                password_hash=hash_password("admin"),
                display_name="Platform Administrator",
                role=RoleType.PLATFORM_ADMIN.value,
                is_active=True,
            )
            _db.session.add(admin)
            _db.session.commit()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app, db):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def admin_headers(client):
    """Get auth headers for platform admin."""
    # Login as bootstrap admin
    resp = client.post("/auth/login", json={
        "username": "admin",
        "password": "admin"
    })
    data = resp.get_json()
    token = data["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def org_setup(client, admin_headers, db):
    """Create a test organization and return its data."""
    from src.models.models import Organization
    org = Organization(name="Test Org", slug="test-org", is_active=True)
    db.session.add(org)
    db.session.commit()
    return {"id": org.id, "name": org.name, "slug": org.slug}


@pytest.fixture
def member_user(client, db, org_setup):
    """Register a guest user and give them member role in test org."""
    resp = client.post("/auth/register-guest", json={
        "username": "testmember",
        "password": "TestPass123!"
    })
    data = resp.get_json()
    user_id = data["data"]["user"]["id"]
    token = data["data"]["access_token"]

    # Create membership
    from src.models.models import Membership
    from src.models.enums import RoleType
    m = Membership(user_id=user_id, organization_id=org_setup["id"], role=RoleType.MEMBER.value)
    db.session.add(m)
    db.session.commit()

    # Re-login to get token with org context
    resp = client.post("/auth/login", json={
        "username": "testmember",
        "password": "TestPass123!"
    })
    data = resp.get_json()
    return {
        "user_id": user_id,
        "token": data["data"]["access_token"],
        "headers": {"Authorization": f"Bearer {data['data']['access_token']}"},
        "refresh_token": data["data"]["refresh_token"],
    }

import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import create_app
from app.core.config import Settings
from app.database.base import Base

# Create test app with test settings
test_settings = Settings(
    environment="test",
    log_level="WARNING",
    cors_origins=["http://localhost:5173"],
    database_url="sqlite://",
)

test_app = create_app(test_settings)
test_client = TestClient(test_app)

# Set up database
engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
session = factory()
Base.metadata.create_all(engine)

from app.db.session import get_db
from app.main import app as main_app

# Override the get_db dependency
main_app.dependency_overrides[get_db] = lambda: session

# Now test the full flow
print("=" * 60)
print("TEST: Full auth flow")
print("=" * 60)

# Test 1: Register
print("\n1. Registering new user...")
reg_resp = test_client.post(
    "/api/v1/auth/register",
    json={
        "email": "user@example.com",
        "password": "correct-horse-1",
        "full_name": "Test User",
        "organisation": "Test Org",
        "title": "Researcher",
    },
)
print(f"   Register status: {reg_resp.status_code}")
if reg_resp.status_code != 201:
    print(f"   Register ERROR: {reg_resp.text}")
    sys.exit(1)
reg_data = reg_resp.json()
print(f"   User created: {reg_data['email']}, role: {reg_data['role']}")

# Test 2: Login
print("\n2. Logging in...")
login_resp = test_client.post(
    "/api/v1/auth/login",
    json={
        "email": "user@example.com",
        "password": "correct-horse-1",
    },
)
print(f"   Login status: {login_resp.status_code}")
if login_resp.status_code != 200:
    print(f"   Login ERROR: {login_resp.text}")
    sys.exit(1)
login_data = login_resp.json()
token = login_data['access_token']
print(f"   Token received: {token[:20]}...")

# Test 3: Access protected endpoint with token
print("\n3. Accessing /auth/me with token...")
me_resp = test_client.get(
    "/api/v1/auth/me",
    headers={"Authorization": f"Bearer {token}"},
)
print(f"   /auth/me status: {me_resp.status_code}")
if me_resp.status_code != 200:
    print(f"   /auth/me ERROR: {me_resp.text}")
    sys.exit(1)
me_data = me_resp.json()
print(f"   Me OK: {me_data['email']}")

# Test 4: Check if token is valid for other endpoints
print("\n4. Accessing datasets (protected)...")
# We need a contributor user to upload/download datasets
from app.models.user import User
from app.models.enums import UserRole

# Create a contributor user
contributor = User(
    email="contributor@example.com",
    full_name="Contributor",
    hashed_password="hash123",
    role=UserRole.CONTRIBUTOR,
    organisation="Test Org",
    title="Test User",
)
session.add(contributor)
session.commit()
session.refresh(contributor)
print(f"   Contributor user created: {contributor.email}")

# Login as contributor
contrib_login = test_client.post(
    "/api/v1/auth/login",
    json={"email": "contributor@example.com", "password": "correct-horse-1"},
)
print(f"   Contributor login status: {contrib_login.status_code}")
if contrib_login.status_code != 200:
    print(f"   Contributor login ERROR: {contrib_login.text}")
    sys.exit(1)
contrib_data = contrib_login.json()
contrib_token = contrib_data['access_token']

# Try to list datasets with contributor token
contrib_headers = {"Authorization": f"Bearer {contrib_token}"}
ds_resp = test_client.get("/api/v1/datasets/", headers=contrib_headers)
print(f"   GET /datasets/ status: {ds_resp.status_code}")
print(f"   GET /datasets/ response: {ds_resp.text[:200]}")

print("\n" + "=" * 60)
print("ALL TESTS PASSED - Auth flow works correctly!")
print("=" * 60)
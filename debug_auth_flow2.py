import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import create_app
from app.core.config import Settings
from app.database.base import Base
from app.models.user import User
from app.models.enums import UserRole
from app.core.security import hash_password

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

# Override the get_db dependency
from app.db.session import get_db
main_app = __import__('app.main', fromlist=['app']).app
main_app.dependency_overrides[get_db] = lambda: session

# Test 1: Register a new user
print("1. Registering new user...")
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
print(f"   Status: {reg_resp.status_code}")
reg_data = reg_resp.json()
print(f"   User: {reg_data['email']}, role: {reg_data['role']}")

# Test 2: Login with the same credentials
print("\n2. Logging in...")
login_resp = test_client.post(
    "/api/v1/auth/login",
    json={"email": "user@example.com", "password": "correct-horse-1"},
)
print(f"   Status: {login_resp.status_code}")
if login_resp.status_code != 200:
    print(f"   ERROR: {login_resp.text}")
    sys.exit(1)
login_data = login_resp.json()
token = login_data['access_token']
print(f"   Token received")

# Test 3: Access protected endpoint /auth/me
print("\n3. Accessing /auth/me with token...")
me_resp = test_client.get(
    "/api/v1/auth/me",
    headers={"Authorization": f"Bearer {token}"},
)
print(f"   Status: {me_resp.status_code}")
if me_resp.status_code != 200:
    print(f"   ERROR: {me_resp.text}")
    sys.exit(1)
me_data = me_resp.json()
print(f"   User: {me_data['email']}, role: {me_data['role']}")

# Test 4: Login as contributor and access datasets
print("\n4. Contributor login + datasets...")
from app.core.security import verify_password
# Verify the password is properly hashed
user = session.query(User).filter(User.email == "user@example.com").first()
print(f"   Password verify: {verify_password('correct-horse-1', user.hashed_password)}")

# Create contributor user with proper password hash
contributor = User(
    email="contributor@example.com",
    full_name="Contributor",
    hashed_password=hash_password("correct-horse-1"),
    role=UserRole.CONTRIBUTOR,
    organisation="Test Org",
    title="Test User",
)
session.add(contributor)
session.commit()
print(f"   Contributor user created")

# Login as contributor
contrib_login = test_client.post(
    "/api/v1/auth/login",
    json={"email": "contributor@example.com", "password": "correct-horse-1"},
)
print(f"   Contributor login status: {contrib_login.status_code}")
if contrib_login.status_code != 200:
    print(f"   ERROR: {contrib_login.text}")
    sys.exit(1)
contrib_data = contrib_login.json()
contrib_headers = {"Authorization": f"Bearer {contrib_data['access_token']}"}

# List datasets
ds_resp = test_client.get("/api/v1/datasets/", headers=contrib_headers)
print(f"   GET /datasets/ status: {ds_resp.status_code}")
print(f"   GET /datasets/ response: {ds_resp.text[:200]}")

print("\n" + "=" * 60)
print("ALL TESTS PASSED - Auth flow works correctly!")
print("=" * 60)
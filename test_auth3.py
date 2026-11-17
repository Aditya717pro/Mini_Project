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

# Test 1: Register a new user
print("=" * 50)
print("TEST 1: Register new user")
print("=" * 50)
register_response = test_client.post(
    "/api/v1/auth/register",
    json={
        "email": "newuser@example.com",
        "password": "correct-horse-1",
        "full_name": "New User",
        "organisation": "Test Org",
        "title": "Researcher",
    },
)
print(f"Register status: {register_response.status_code}")
print(f"Register response: {register_response.text[:300]}")

# Test 2: Login
print("\n" + "=" * 50)
print("TEST 2: Login")
print("=" * 50)
login_response = test_client.post(
    "/api/v1/auth/login",
    json={
        "email": "newuser@example.com",
        "password": "correct-horse-1",
    },
)
print(f"Login status: {login_response.status_code}")
if login_response.status_code == 200:
    data = login_response.json()
    print(f"Login OK!")
    print(f"  User: {data['user']['email']}")
    print(f"  Token preview: {data['access_token'][:20]}...")
    
    # Test 3: Access protected endpoint /auth/me
    print("\n" + "=" * 50)
    print("TEST 3: Access /auth/me (protected)")
    print("=" * 50)
    me_response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    print(f"Me status: {me_response.status_code}")
    if me_response.status_code == 200:
        print(f"Me OK: User email = {me_response.json()['email']}")
    else:
        print(f"Me error: {me_response.text}")
else:
    print("Login failed - cannot continue")
PYEOF
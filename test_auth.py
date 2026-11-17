import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

from fastapi.testclient import TestClient
from app.main import app as fastapi_app
from app.core.config import Settings

# Create test app with test settings
test_settings = Settings(
    environment="test",
    log_level="WARNING",
    cors_origins=["http://localhost:5173"],
    database_url="sqlite://",
)

# Override the app's settings
app = fastapi_app
# We need to set up the test database

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
session = factory()

from app.database.base import Base
Base.metadata.create_all(engine)

# Override the get_db dependency
from app.db.session import get_db
app.dependency_overrides[get_db] = lambda: session

from app.tests.test_workflows import create_user, login

test_client = TestClient(app)

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
print(f"Register response: {register_response.text[:200]}")

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
    print(f"  Token: {data['access_token'][:20]}...")
    print(f"  User: {data['user']['email']}")
    
    # Test 3: Access protected endpoint
    print("\n" + "=" * 50)
    print("TEST 3: Access /auth/me")
    print("=" * 50)
    me_response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    print(f"Me status: {me_response.status_code}")
    if me_response.status_code == 200:
        print(f"Me OK: {me_response.json()['email']}")
    else:
        print(f"Me error: {me_response.text}")
    
    # Test 4: Create a dataset
    print("\n" + "=" * 50)
    print("TEST 4: Create dataset")
    print("=" * 50)
    from app.tests.test_workflows import create_user as create_user_tw
    from app.models.enums import UserRole
    
    # We need a contributor user to upload datasets
    contributor = create_user_tw(session, "contributor@example.com", UserRole.CONTRIBUTOR)
    
    # Login as contributor
    contrib_login = test_client.post(
        "/api/v1/auth/login",
        json={"email": "contributor@example.com", "password": "correct-horse-1"},
    )
    print(f"Contributor login status: {contrib_login.status_code}")
    if contrib_login.status_code == 200:
        contrib_data = contrib_login.json()
        contrib_headers = {"Authorization": f"Bearer {contrib_data['access_token']}"}
        
        # Upload a dataset
        csv_content = "participant_id,age,sex,region,visit_date,outcome,weight_kg,notes\nP001,34,Female,England,2025-01-01,0,61.2,ok\n"
        metadata = {
            "title": "Synthetic Women's Health Cohort",
            "description": "Synthetic test dataset with no real patient data.",
            "domain": "Women's health",
            "access": "Controlled",
            "tags": ["synthetic", "test"],
            "age_range": "18-45 years",
            "geography": ["England"],
            "study_design": "Retrospective cohort",
            "license": "Synthetic research use only",
            "ethics_approved": True,
            "data_dictionary_available": True,
            "intended_tasks": ["Readmission risk modelling"],
            "label_column": "outcome",
            "research_task": "Readmission risk modelling",
        }
        
        upload = test_client.post(
            "/api/v1/datasets/",
            headers=contrib_headers,
            files={"file": ("synthetic.csv", csv_content.encode(), "text/csv")},
            data={"metadata": metadata},  # Note: metadata should be json.dumps in actual use
        )
        print(f"Upload status: {upload.status_code}")
        print(f"Upload response: {upload.text[:200]}")
    else:
        print("Contributor login failed")
else:
    print("Login failed")
PYEOF
import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import app as fastapi_app
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

# Set up database
engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
session = factory()
Base.metadata.create_all(engine)

# Override the get_db dependency
from app.db.session import get_db
# We need to access the app to set the override
# Let's just use the test client directly

from app.main import create_app

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
   
    # Test 4: Create a contributor user and upload dataset
    print("\n" + "=" * 50)
    print("TEST 4: Create contributor and upload dataset")
    print("=" * 50)
    
    # Create a contributor user manually
    contributor = User(
        email="contributor@example.com",
        full_name="Contributor",
        hashed_password="hash123",  # In reality, this would be properly hashed
        role=UserRole.CONTRIBUTOR,
        organisation="Test Org",
        title="Test User",
    )
    session.add(contributor)
    session.commit()
    session.refresh(contributor)
    print(f"Created contributor: {contributor.email}")
    
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
        
        # Note: The actual API expects metadata as a JSON string form field
        upload = test_client.post(
            "/api/v1/datasets/",
            headers=contrib_headers if 'contrib_headers' in dir() else {},
            files={"file": ("synthetic.csv", csv_content.encode(), "text/csv")},
            data={"metadata": metadata},  # This might need to be json.dumps(metadata)
        )
        print(f"Upload status: {upload.status_code}")
        print(f"Upload response: {upload.text[:300]}")
    else:
        print("Contributor login failed")
else:
    print("Login failed - cannot continue")
PYEOF
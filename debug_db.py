import json
import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import app
from app.core.config import Settings

# Override settings for test
settings = Settings(
    environment="test",
    log_level="WARNING",
    cors_origins=["http://localhost:5173"],
    database_url="sqlite://",
    raw_storage_dir=None,
    processed_storage_dir=None,
)

engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
session = factory()

from app.database.base import Base
Base.metadata.create_all(engine)

# Override app dependency
app.dependency_overrides = {}
app.dependency_overrides[None] = lambda: session  # just a placeholder

from app.api.deps import get_db
app.dependency_overrides[get_db] = lambda: session

from app.main import create_app
test_app = create_app(settings)
test_client = TestClient(test_app)

# Now try to create a user and upload
from app.models.user import User
from app.models.enums import UserRole
from app.core.security import hash_password

with session as db:
    user = User(
        email='test@test.com',
        full_name='Test User',
        hashed_password='hash123',
        role=UserRole.CONTRIBUTOR,
        organisation='Test Org',
        title='Test User',
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f'Created user: {user.id}')
    
    # Try to upload a dataset
    csv_content = 'participant_id,age,sex,region,visit_date,outcome,weight_kg,notes\nP001,34,Female,England,2025-01-01,0,61.2,ok\n'
    metadata = {
        'title': 'Test Dataset',
        'description': 'Test',
        'domain': "Women's health",
        'access': 'Controlled',
        'tags': ['test'],
        'age_range': '18-45 years',
        'geography': ['England'],
        'study_design': 'Retrospective cohort',
        'license': 'Synthetic',
        'ethics_approved': True,
        'data_dictionary_available': True,
        'intended_tasks': ['Readmission risk modelling'],
        'label_column': 'outcome',
        'research_task': 'Readmission risk modelling',
    }
    
    # Need to set the app dependency override properly
    # Let's just directly check if we can create a dataset
    from app.models.dataset import Dataset
    from app.services.upload_service import create_upload
    from app.core.config import get_settings
    
    # Check create_upload function
    print(f'User role: {user.role}')
    print(f'User ID: {user.id}')
    
    # Try creating a dataset directly
    dataset = Dataset(
        id='test-uuid-1234',
        owner_id=user.id,
        title='Test',
        description='Test',
        domain='Women\'s health',
        access_classification='Controlled',
        status='Processing',
        format='CSV',
        original_filename='test.csv',
        original_path='',
        checksum_sha256='abc123',
        file_size_bytes=100,
        record_count=1,
        column_count=1,
        current_version_number=1,
        missing_rate=0.0,
        duplicate_rate=0.0,
        research_task='Readmission risk modelling',
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    print(f'Created dataset: {dataset.id}, status: {dataset.status}')
    print(f'Can query: {session.get(Dataset, dataset.id) is not None}')
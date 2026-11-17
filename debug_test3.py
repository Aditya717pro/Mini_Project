import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')
sys.path.insert(0, 'D:\\Mini_Project')

from app.tests.conftest import create_app, db_session
from app.core.config import Settings

# Create app with test config
app = create_app(
    Settings(
        environment='test',
        log_level='WARNING',
        cors_origins=['http://localhost:5173'],
        database_url='sqlite://',
    )
)
print('App created OK')

# Now try db_session
with db_session as session:
    print(f'Session OK: {session is not None}')
    from app.models.user import User
    from app.models.enums import UserRole
    from app.core.security import hash_password
    
    user = User(
        email='test@test.com',
        full_name='Test User',
        hashed_password='hash123',
        role=UserRole.CONTRIBUTOR,
        organisation='Test Org',
        title='Test User',
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    print(f'User created: {user.id}')
    
    # Try creating a dataset
    from app.models.dataset import Dataset
    dataset = Dataset(
        id='test-uuid-1234',
        owner_id=user.id,
        title='Test',
        description='Test',
        domain='Womens health',
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
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    print(f'Dataset created: {dataset.id}, status: {dataset.status}')
    print(f'Can query by id: {session.get(Dataset, dataset.id) is not None}')
    print(f'Query all datasets count: {session.query(Dataset).count()}')
PYEOF
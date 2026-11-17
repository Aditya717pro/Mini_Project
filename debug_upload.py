import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.database.base import Base
from app.models.user import User
from app.models.enums import UserRole
from app.core.security import hash_password
from app.services.user_service import create_user as create_user_service

engine = create_engine('sqlite:///./test_debug.db')
Base.metadata.create_all(engine)

from app.main import app
client = TestClient(app)

# We need to set up a contributor user first
with Session(engine) as db:
    # Create contributor
    contributor = create_user_service(db, 'contrib@test.com', 'password123', UserRole.CONTRIBUTOR, 'Test Orgn', 'Test User')
    db.commit()
    
    # Login
    login_resp = client.post('/api/v1/auth/login', json={'email': 'contrib@test.com', 'password': 'password123'})
    print(f'Login status: {login_resp.status_code}')
    data = login_resp.json()
    print(f'Login response keys: {list(data.keys())}')
    token = data['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    
    # Now upload a dataset
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
    
    upload = client.post(
        '/api/v1/datasets/',
        headers=headers,
        files={'file': ('synthetic.csv', csv_content.encode(), 'text/csv')},
        data={'metadata': json.dumps(metadata)},
    )
    print(f'Upload status: {upload.status_code}')
    print(f'Upload response: {upload.text}')
    payload = upload.json()
    print(f'Dataset status from response: {payload["dataset"]["status"]}')
    print(f'Full dataset JSON: {json.dumps(payload["dataset"], indent=2)}')
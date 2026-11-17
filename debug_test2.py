import json
import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import app
from app.models import User
from app.models.enums import UserRole
from app.core.security import hash_password

engine = create_engine('sqlite:///./test_debug2.db')
Base = None

from app.database.base import Base

Base.metadata.create_all(engine)

with Session(engine) as db:
    # Create users manually
    contributor = User(
        email='contributor@test.com',
        full_name='Contributor',
        hashed_password='hash123',
        role=UserRole.CONTRIBUTOR,
        organisation='Test Org',
        title='Test User',
    )
    db.add(contributor)
    db.commit()
    
    # Login - we need to generate a token manually
    # Let's just check the dataset creation
    
    csv_content = (
        "participant_id,age,sex,region,visit_date,outcome,weight_kg,notes\n"
        "P001,34,Female,England,2025-01-01,0,61.2,ok\n"
    )
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
    
    # We need to POST to /api/v1/datasets/
    # But we need auth headers. Let's check if there's a simpler way.
    # For now, let's just check the route directly
    
print('Test setup done')
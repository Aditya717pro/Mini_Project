import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.tests.test_workflows import create_user, login
from app.models.enums import UserRole

engine = create_engine('sqlite:///./test_debug2.db')

from app.main import app
client = TestClient(app)

with Session(engine) as db:
    contributor = create_user(db, 'contributor@test.com', UserRole.CONTRIBUTOR)
    researcher = create_user(db, 'researcher@test.com', UserRole.RESEARCHER)
    admin = create_user(db, 'admin@test.com', UserRole.ADMINISTRATOR)
    
    contributor_headers = login(client, contributor.email)
    researcher_headers = login(client, researcher.email)
    admin_headers = login(client, admin.email)
    
    csv_content = (
        "participant_id,age,sex,region,visit_date,outcome,weight_kg,notes\n"
        "P001,34,Female,England,2025-01-01,0,61.2,ok\n"
        "P002,29,Female,England,2025-01-02,1,58.0,follow-up\n"
        "P003,,Male,Scotland,2025-01-03,0,70.5,missing age\n"
        "P004,41,Male,Wales,not-a-date,1,82.1,date issue\n"
        "P005,34,Female,England,2025-01-01,0,61.2,ok\n"
    )
    metadata = {
        "title": "Synthetic Women's Health Cohort",
        "description": "Synthetic test dataset with no real patient data.",
        "domain": "Women's health",
        "access": "Controlled",
        "tags": ["synthetic", "test"],
        "age_range": "18-45 years",
        "geography": ["England", "Scotland", "Wales"],
        "study_design": "Retrospective cohort",
        "license": "Synthetic research use only",
        "ethics_approved": True,
        "data_dictionary_available": True,
        "intended_tasks": ["Readmission risk modelling"],
        "label_column": "outcome",
        "research_task": "Readmission risk modelling",
    }
    upload = client.post(
        "/api/v1/datasets/",
        headers=contributor_headers,
        files={"file": ("synthetic.csv", csv_content.encode(), "text/csv")},
        data={"metadata": json.dumps(metadata)},
    )
    print(f'Upload status: {upload.status_code}')
    payload = upload.json()
    print(f'Dataset status: {payload["dataset"]["status"]!r}')
    print(f'Full dataset: {json.dumps(payload["dataset"], indent=2)}')
    job_id = payload["jobId"]
    
    # Check job status
    job = client.get(f"/api/v1/etl/jobs/{job_id}", headers=contributor_headers)
    print(f'Job status: {job.json()["status"]!r}')
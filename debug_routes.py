import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

engine = create_engine('sqlite:///./test_debug.db')

from app.main import app
client = TestClient(app)

print('App routes:')
for route in app.routes:
    if hasattr(route, 'methods'):
        methods = list(route.methods)
        print(f'  {methods} {getattr(route, "path", "unknown")}')
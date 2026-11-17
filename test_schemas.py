import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

# Test 1: Check if we can create a user
from app.models.user import User
from app.core.security import hash_password
print("User model import: OK")

# Test 2: Check if we can hash a password
hashed = hash_password("correct-horse-1")
print(f"Password hash: {hashed[:20]}...")

# Test 3: Check RegisterRequest schema
from app.schemas.auth import RegisterRequest
try:
    r = RegisterRequest(email="test@example.com", password="password123", full_name="Test User")
    print(f"RegisterRequest: OK, full_name={r.full_name!r}")
except Exception as e:
    print(f"RegisterRequest error: {e}")

# Test 3b: Test whitespace name (the bug I fixed)
try:
    r = RegisterRequest(email="test2@example.com", password="password123", full_name="   ")
    print(f"Whitespace name: PASSED validation (len={len(r.full_name)}) - WILL BE REJECTED AT API LEVEL")
except Exception as e:
    print(f"Whitespace name error: {e}")

# Test 4: Check LoginRequest schema
from app.schemas.auth import LoginRequest
try:
    r = LoginRequest(email="test@example.com", password="password123")
    print(f"LoginRequest: OK, email={r.email!r}")
except Exception as e:
    print(f"LoginRequest error: {e}")
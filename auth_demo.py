import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

# Read the DemoStore file and look for auth state
with open('D:\\Mini_Project\\frontend\\src\\store\\DemoStore.tsx', 'r') as f:
    lines = f.readlines()

# Print lines around key auth functions
for i, line in enumerate(lines, 1):
    if any(keyword in line.lower() for keyword in ['login', 'logout', 'token', 'user', 'setuser', 'setrole']):
        print(f"{i}: {line.rstrip()}")
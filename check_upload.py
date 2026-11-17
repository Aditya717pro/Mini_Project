import sys
sys.path.insert(0, 'D:\\Mini_Project\\backend')

# Read the UploadDataset file and check for sidebar/signout
with open('D:\\Mini_Project\\frontend\\src\\pages\\UploadDataset.tsx', 'r') as f:
    content = f.read()

# Look for the aside/sidebar section
import re
# Find the aside class="upload-side" section
match = re.search(r'<aside class="upload-side">(.*?)</aside>', content, re.DOTALL)
if match:
    print("Found upload-side aside section")
    print(match.group(1)[:1000])
    
# Look for any existing logout/logout related code
if 'logout' in content.lower():
    print("\n\nLogout-related code found:")
    for i, line in enumerate(content.split('\n'), 1):
        if 'logout' in line.lower():
            print(f"{i}: {line[:100]}")
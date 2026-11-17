import subprocess
result = subprocess.run(
    ['D:\\Mini_Project\\backend\\.venv\\Scripts\\python.exe', '-m', 'pytest', 'D:\\Mini_Project\\backend\\tests'],
    capture_output=True, text=True, cwd='D:\\Mini_Project'
)
print('STDOUT:')
print(result.stdout)
print('STDERR:')
print(result.stderr)
print('Return code:', result.returncode)
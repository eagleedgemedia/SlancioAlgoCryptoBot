import os

replacements = {
    "Slancio Crypto Algo Treding Engine": "Slancio Crypto Algo Treding Engine",
    "SLANCIO CRYPTO ALGO TREDING ENGINE": "SLANCIO CRYPTO ALGO TREDING ENGINE",
    "Slancio Algo Engine": "Slancio Algo Engine",
    "Slancio Algo": "Slancio Algo"
}

def replace_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    original = content
    for old, new in replacements.items():
        content = content.replace(old, new)
        
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, dirs, files in os.walk('.'):
    if 'alembic' in root or '.git' in root or '__pycache__' in root or '.pytest_cache' in root:
        continue
    for file in files:
        if file.endswith(('.py', '.html', '.js', '.css', '.md', '.txt')):
            replace_in_file(os.path.join(root, file))

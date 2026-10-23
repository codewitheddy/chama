"""
Called by build.bat to inject a fresh SECRET_KEY into desktop.env.
Usage: python update_secret_key.py
"""
import re
import secrets

key = secrets.token_urlsafe(50)
path = 'desktop.env'

with open(path, 'r') as f:
    content = f.read()

new_content = re.sub(
    r'^SECRET_KEY=.*',
    f'SECRET_KEY={key}',
    content,
    flags=re.MULTILINE,
)

with open(path, 'w') as f:
    f.write(new_content)

print(f'  SECRET_KEY updated ({len(key)} chars).')

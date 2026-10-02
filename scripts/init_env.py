"""Initialize local configuration once; preserve an existing environment."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / '.env'
if not target.exists():
    content = (root / '.env.example').read_text()
    content = content.replace('django-insecure-local-template-replace-with-generated-key', secrets.token_urlsafe(48))
    target.write_text(content)
    print('Created local environment. Configure AI, email and sandbox as needed.')
else:
    print('Existing local environment preserved.')

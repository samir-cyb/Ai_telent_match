"""Create private Judge0 configuration once, without resetting existing volumes."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / 'judge0.local.conf'
if target.exists():
    raise SystemExit('judge0.local.conf already exists; preserve its database credentials.')
values = {'POSTGRES_PASSWORD': secrets.token_hex(32), 'REDIS_PASSWORD': secrets.token_hex(32),
          'SECRET_KEY_BASE': secrets.token_hex(64), 'AUTHN_TOKEN': secrets.token_urlsafe(48)}
lines = (root / 'judge0.conf').read_text().splitlines()
for key, value in values.items():
    lines = [line for line in lines if not line.startswith(key + '=')]
    lines.append(key + '=' + value)
target.write_text('\n'.join(lines) + '\n')
target.chmod(0o600)
env = root / '.env'
if not env.exists():
    env.write_text((root / '.env.example').read_text().replace('django-insecure-local-template-replace-with-generated-key', secrets.token_urlsafe(48)))
lines = [line for line in env.read_text().splitlines() if not line.startswith('JUDGE0_AUTH_TOKEN=')]
lines.append('JUDGE0_AUTH_TOKEN=' + values['AUTHN_TOKEN'])
env.write_text('\n'.join(lines) + '\n')
print('Private sandbox configuration created. Run docker compose -f docker-compose.judge0.yml up -d')

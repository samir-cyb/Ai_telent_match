# AI Talent Match

Django student/company/admin application. Repairs preserve the existing
matching engine, fraud analysis, optional coding/quiz assessment, interview,
pipeline ranking and hire/reject Q-learning feedback calculations.

## Start on Windows

Use Python 3.12. For the full project ZIP, extract it into a new folder and open
PowerShell in the extracted `Ai_telent_match` folder. Git is not required to run
the ZIP. Start with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/`. A new ZIP installation has an empty database;
register your own student/company account. Your existing accounts and CVs are
in your old database/uploads and are not included in this package. See the
package's `PC-TEST-GUIDE.md` for acceptance checks and upgrade instructions.

If the repair branch has already been published to GitHub, the alternative is:

```powershell
git clone https://github.com/samir-cyb/Ai_telent_match.git
cd Ai_telent_match
git switch codex/system-repairs
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\python.exe manage.py runserver
```

If local PowerShell policy blocks the setup script, run these ordinary commands:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\init_env.py
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check_setup
.\.venv\Scripts\python.exe manage.py runserver
```

Linux/macOS: `bash scripts/setup.sh`, then `.venv/bin/python manage.py runserver`.
Scripts preserve an existing `.env` and database. They do not create demo users.
Use the existing registration pages; create a platform admin with:

```powershell
.\.venv\Scripts\python.exe manage.py create_platform_admin --email you@example.com --super-admin
```

The command prompts privately for a password. Platform admins are separate
from Django's `/admin/` superuser accounts. There is no fixed admin password.

## External services

The site can start with SQLite and the console email backend. To operate the
full system, configure the existing services in your private `.env`:

| Feature | Required configuration |
|---|---|
| CV, LinkedIn PDF and AI tasks | Ollama text/vision models, or `LLM_PREFER_LOCAL=false` and a Gemini key with the Ollama fallback configured |
| GitHub projects | Save a username or GitHub profile URL, then Refresh from GitHub. `GITHUB_TOKEN` is optional for public repos; rate limits still apply |
| Coding Run/Submit, all languages | Judge0; candidate code is never run on the Django host |
| Actual email delivery | SMTP backend, host, private credentials and public `SITE_URL` |
| Optional existing chat | `ENABLE_CHAT=true`, ASGI/Daphne, Redis for multiple processes |

For local AI: install Ollama, run `ollama pull qwen2.5:3b` and
`ollama pull gemma3:4b`, then start Ollama. The existing local-first preference
is preserved. Adjust `LLM_TIMEOUT_SECONDS` for your machine. Local PDF vision
renders pages as PNG (at most 20 pages); text extraction remains a fallback.

CV parsing fills a review modal. **Save** persists profile lists. Imported CV
items merge with existing entries; explicit deletion from the edit modal still
works. Profile fields load before career prediction finishes.

For Judge0 on a Linux Docker host (Windows uses Docker Desktop's Linux engine):

```powershell
.\.venv\Scripts\python.exe scripts\prepare_sandbox.py
docker compose -f docker-compose.judge0.yml up -d
```

The helper generates ignored private configuration and sets the matching local
API token. Preserve credentials for existing Judge0 database/Redis volumes;
do not reset or replace them blindly. This Compose file uses PostgreSQL 16
for a fresh sandbox. An existing PostgreSQL 13 sandbox volume needs an explicit
dump/restore into a new volume before this image upgrade; do not attach its old
data directory to PostgreSQL 16. Keep the old volume until the restore is checked. The API binds to loopback. For deployment
place privileged Judge0 workers on a separate host with no application secrets
or user data mounted, and restrict access to the Django backend.

## Updating an existing installation

Back up the database and uploads before migration. Pull the repair branch,
install its requirements, then run `manage.py migrate` and `manage.py check_setup`.
Migration 0022 stops if old duplicate student/job applications exist; reconcile
their assessments/interviews after review, then retry. It never deletes those
records. PostgreSQL 14+ is supported through `DB_ENGINE=postgresql` and `DB_*`.
SQLite is the local development default; use PostgreSQL for concurrent hiring.

Applicant counters now follow application inserts/deletes across all paths.
`check_setup` reports older inaccurate counts for reconciliation; it does not
silently rewrite historical data. Preview corrections with
`manage.py reconcile_applicant_counts`, then add `--apply` after review.

## Deployment and scheduled matching

Set `DEBUG=false`, a unique strong `SECRET_KEY`, exact `ALLOWED_HOSTS`, HTTPS,
public `SITE_URL`, SMTP and PostgreSQL. Add exact trusted origins only if
needed. Configure the reverse proxy to serve `/static/`, **never expose
`MEDIA_ROOT` directly**: `/media/` CV access is checked by Django. Only the
student, their hiring company with an application, and platform admins may
download those documents. Run `manage.py check --deploy` before deployment.

Rotate previously committed Gemini keys and fixed admin credentials through
their providers/accounts. Removing literals from this branch does not remove
them from Git history or revoke them. For an existing platform admin, use
`manage.py change_platform_admin_password --email you@example.com`; it also
revokes that account's server sessions.

Existing `manage.py daily_matching` remains the scheduler entry point. Run it
once daily using Windows Task Scheduler or cron with the project's venv,
working directory and private environment. Prevent overlapping instances and
monitor its logs. Merely setting Redis/Celery variables does not schedule it;
no new worker architecture is introduced by these repairs.

## Validation

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test core vetting --settings=Ai_telent_match.test_settings
```

Tests use an isolated in-memory SQLite database and mock external services;
they do not modify the real database or call paid AI. See
[`docs/REPAIR_PLAN.md`](docs/REPAIR_PLAN.md) and
[`docs/REPAIR_RESULTS.md`](docs/REPAIR_RESULTS.md) for scope and evidence.
Optional research dependencies are in `requirements-analysis.txt`.


## How to setup this

### Requirements

- Python 3.12
- Git
- Windows PowerShell

### 1. Download the project

```powershell
git clone https://github.com/samir-cyb/Ai_telent_match.git
cd Ai_telent_match
```

If you already have the repository, save your local changes before updating:

```powershell
git switch main
git pull origin main
```

The latest updates must be merged into `main` before pulling.

### 2. Run the setup script

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

This script creates `.venv`, installs dependencies, creates a local `.env` if one does not exist, runs database migrations, and checks the setup. Existing `.env` files are preserved.

If the setup script fails, use these commands instead:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\init_env.py
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check_setup
```

### 3. Configure your local environment

Open the generated `.env` file. SQLite is the default database, so a separate database server is not required for local setup.

To use Gemini for AI features, configure:

```dotenv
LLM_PREFER_LOCAL=false
GEMINI_API_KEY=your_own_gemini_api_key
```

The configured Gemini models must be available to your API key.

Alternatively, to use local AI, install and start Ollama, then download the configured models:

```powershell
ollama pull qwen2.5:3b
ollama pull gemma3:4b
```

Keep `LLM_PREFER_LOCAL=true` when using local AI.

Other feature requirements:

- **GitHub imports:** Add a GitHub username or profile URL in the student profile, then use Refresh from GitHub. An optional `GITHUB_TOKEN` can help with API rate limits.
- **Coding assessments:** Require a running Judge0 service and the matching configuration in `.env`.
- **Email delivery:** Requires SMTP configuration. The default console backend prints emails in the terminal.
- **Optional chat:** Requires its Redis/ASGI configuration when enabled.

Never commit `.env`, API keys, passwords, your virtual environment, database, or uploaded CVs.

### 4. Start the server

```powershell
.\.venv\Scripts\python.exe manage.py check_setup
.\.venv\Scripts\python.exe manage.py runserver
```

Open:

http://127.0.0.1:8000/

A fresh installation has an empty database. Register your own student or company account. Existing users, jobs, applications, and uploaded CVs are not included in Git.

### 5. Verify the installation

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test core vetting --settings=Ai_telent_match.test_settings
```

The tests use an isolated test database and mock external services. Verify AI features separately with your configured provider.

### 6. Update your existing installation

Back up your database and uploaded files, and commit or stash any local code changes before updating.

```powershell
git switch main
git pull origin main
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check_setup
.\.venv\Scripts\python.exe manage.py runserver
```

If a command fails, resolve the reported error before continuing. Keep your existing `.env`; check `.env.example` for any newly required settings.


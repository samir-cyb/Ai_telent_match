# AI Talent Match — Project Handoff Document
**Last updated:** June 22, 2026  
**Prepared by:** Claude (Cowork AI session)  
**For:** Next developer, collaborator, or continuation session

---

## 1. What This Project Is

**AI Talent Match** is a full-stack Django web application that acts as an AI-powered recruitment platform connecting university students with companies. It is not a job board — it is an intelligent matching and screening system.

The core idea: instead of students submitting generic CVs and companies manually reviewing hundreds of applications, the system uses AI, reinforcement learning, and multi-source signal extraction to match students to jobs with scored, explainable results — and continuously improves based on hiring outcomes.

The platform serves three roles:
- **Students** — build profiles, upload CVs/LinkedIn PDFs, get matched to jobs, take AI interviews, receive career coaching
- **Companies** — post jobs, see AI-ranked applicants, run automated vetting tests, trigger recruitment agents, and hire/reject with one click
- **Admins** — monitor fraud, review analytics, manage the platform

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2 (Python) |
| Database | PostgreSQL (via psycopg2) |
| AI/LLM | Google Gemini (gemini-1.5-flash / google-generativeai) |
| Matching Engine | Custom NumPy + scikit-learn |
| Auth | Custom JWT-style session (no django-auth) |
| Storage | Local filesystem (resumes/, linkedin_pdfs/, media/) |
| Email | SMTP via Django email backend |
| Frontend | HTML/CSS/JS (no React — server-rendered templates + vanilla JS) |
| Task Queue | Celery + Redis (configured, partially used) |
| Deployment | gunicorn (production), daphne + channels (WebSocket-ready) |
| External APIs | GitHub API (scraping), Supabase (partial), OpenAI (partial) |

---

## 3. Project Structure

```
Ai_telent_match/
├── core/                        # Main app — all business logic
│   ├── models.py                # All database models
│   ├── views.py                 # All views (student, company, admin, API)
│   ├── urls.py                  # Core API routes
│   ├── utils/
│   │   ├── ai_engine.py         # RL-weighted matching engine
│   │   ├── recruitment_agent.py # 7-step autonomous recruitment agent
│   │   ├── interview_generator.py # AI interview question gen + scoring
│   │   ├── github_scraper.py    # GitHub API validator
│   │   ├── linkedin_parser.py   # LinkedIn PDF extractor
│   │   ├── resume_parser.py     # CV PDF extractor
│   │   ├── fraud_detector.py    # Fraud detection logic
│   │   ├── ai_effectiveness.py  # AI effectiveness reporting
│   │   ├── points.py            # Leaderboard points system
│   │   └── email_helpers.py     # Email notification helpers
│   └── migrations/              # 18 migrations (0001–0018 merge)
│
├── vetting/                     # Technical assessment sub-app
│   ├── models.py                # VettingChallenge, VettingSession, VettingResult
│   ├── views.py                 # All vetting views
│   ├── services.py              # QuestionGenerator, CodeExecutor, CodeGrader
│   └── urls.py
│
├── templates/
│   ├── base.html                # Shared layout with nav + notification panel
│   ├── student/                 # dashboard, profile, jobs, leaderboard, career_advisor
│   ├── company/                 # dashboard, applicants, ai_agent, agent_run_detail, etc.
│   ├── interviews/              # candidate_interview, interview_done
│   ├── vetting/                 # ide, quiz, result, error
│   ├── admin/                   # dashboard, analytics, fraud_review
│   └── email/                   # Email notification templates
│
├── Ai_telent_match/
│   ├── settings.py
│   └── urls.py                  # Root URL config
│
├── poster/                      # Academic poster assets (separate from Django app)
│   ├── index.html
│   ├── build_poster.js          # PowerPoint generation script
│   └── rl_weights.py            # Matplotlib chart for poster
│
└── requirements.txt
```

---

## 4. Key Models (core/models.py)

### Student
The central model. Key fields:
- `department_category` — auto-maps department string to one of: `tech, engineering, business, design, science, humanities, any`
- `trust_score` — computed composite score (profile completeness + activity + project quality)
- `github_verified`, `github_score` — from GitHub API validation
- `linkedin_score`, `linkedin_parsed_data` — from LinkedIn PDF upload
- `profile_complete_score` — drives matching weight

### Company
- `custom_weights` — JSON overriding the default RL weights per feature (skills, cgpa, projects, activity, trust)
- `ai_feedback_signal` — tracks hire/reject patterns for RL updates

### Job
- `department_category` — determines which default weight set is used
- `custom_weights` — job-level weight override (highest priority)
- `required_skills` — ManyToMany with Skill

### Application
- `match_score`, `match_explanation` — set by AI engine on apply
- `vetting_score` — set after coding/MCQ test
- `ai_agent_decision` — `shortlist / reject / review` from the 7-step agent
- `status` — `applied → shortlisted → interviewed → hired / rejected`

### AIFeedbackLog
Records every hire/reject signal for RL weight adaptation. Fields: `feature_scores`, `weight_used`, `outcome` (hire/reject), `delta` (weight change applied).

### RecruitmentAgentRun
Logs every agent execution: `thought_log` (JSON array of step outputs), `decision`, `fit_report`, `weight_snapshot_before`, `weight_snapshot_after`.

### AIInterview
AI-generated interview (via Gemini). Fields: `token` (URL access), `questions` (JSON), `answers`, `scores`, `expires_at`, `cheating_log` (anti-cheat violations), `gemini_analysis` (full Gemini review).

### ScheduledInterview
Offline interview scheduling by company. Fields: `interview_date`, `interview_time`, `location`, `contact_person`, `mode` (offline only — online was removed).

### LeaderboardEntry
Student gamification. `total_points`, `awarded_actions` (list of already-rewarded actions to prevent double-awarding).

### InterviewSlot
Company pre-defines slots (date + time range + duration). Students book from available slots.

---

## 5. Core AI Systems

### 5.1 Matching Engine (ai_engine.py)

Weight system with 3-level priority:
1. Department defaults (e.g., tech jobs weight skills 40%, design jobs weight projects 45%)
2. Company custom weights (override department defaults)
3. Job custom weights (override everything)

Feature scores computed: `skills` (semantic match with TF-IDF + ecosystem expansion), `cgpa` (normalized against job min), `projects` (GitHub-validated), `activity` (login frequency + application history), `trust` (composite of github + linkedin + profile completeness).

### 5.2 RL Weight Adaptation

After every hire or reject signal:
- Hire → increase weights of features where the hired student scored high
- Reject → decrease weights of features where the rejected student scored high
- Learning rate: 0.05, bounded 0.05–0.60 per feature
- Stored in Company.custom_weights and logged in AIFeedbackLog

### 5.3 7-Step Recruitment Agent (recruitment_agent.py)

Runs autonomously when triggered:
1. Gather candidate profile
2. Analyse job requirements
3. Compute feature scores
4. Apply RL-learned weights
5. Make shortlist/reject/review decision
6. Generate fit report (strengths, gaps, Gemini narrative)
7. Auto-update application status

Skill ecosystem expansion: if job requires Python → students with TensorFlow, Django, pandas etc. get partial credit.

### 5.4 AI Interview (interview_generator.py)

- Company triggers interview generation (via agent run detail page)
- Gemini generates N questions per role/department
- Candidate gets a token-based URL with one question at a time
- Anti-cheat: fullscreen enforcement, tab-switch detection, copy-paste blocking, auto-submit on violations
- Company sees per-answer scores + Gemini full analysis on result page

### 5.5 Technical Vetting (vetting app)

Three types of challenges: `coding` (Python subprocess executor), `mcq` (multiple choice), `written` (text-based).

CodeGrader: runs test cases → static analysis (complexity, security scan) → AI review via Gemini → smart partial credit scoring.

---

## 6. Current State (as of June 22, 2026)

### What is fully working
- Student registration, login, profile building (CGPA, skills, projects, GitHub, LinkedIn PDF, resume)
- Company registration, login, job posting with department + weight config
- AI matching on apply (score + explanation stored)
- Hire/Reject/Manual signals → RL weight update
- AI Agent visualization page (weight chart, learning curve)
- 7-step Recruitment Agent with thought log + fit report
- AI Interview: generate → send link → candidate takes → company views result
- Anti-cheat system for AI interviews
- Technical vetting: coding IDE + MCQ quiz + written assessment
- Vetting result page with layer breakdown (test cases / static / AI)
- Notifications panel with polling + toast popups
- AI Career Advisor Chatbot (floating bubble + full page, Gemini-powered)
- Skill Demand Heatmap for company dashboard
- Student Leaderboard with points system
- AI Career Coach / Career Trajectory on student dashboard
- LinkedIn PDF upload and scoring
- Smart job recommendations
- GitHub validation via API
- Admin dashboard: fraud review, analytics
- Email notifications (application, shortlist, hire, reject, interview scheduled)
- Academic poster (HTML/CSS/JS + PowerPoint + matplotlib chart)

### What is partially done or broken
- **5 template files still have git merge conflict markers** (not yet resolved):
  - `templates/student/profile.html`
  - `templates/student/dashboard.html`
  - `templates/company/dashboard.html`
  - `templates/company/applicants.html`
  - `templates/base.html`
- **core/utils/github_scraper.py** — has merge conflicts (multiple unresolved blocks)
- **core/migrations/0002** — has a merge conflict marker (may block migrations)
- **`student_leaderboard` view** — imported in urls.py but needs to be confirmed it exists in views.py
- **`AIEffectivenessView` and `LeaderboardView`** — added to core/urls.py but may not be implemented in views.py
- **`company_interview_result` view** — wired but needs verification the view function exists
- **`WeightAgentDataView`** — wired in urls, needs verification
- `award_points` in vetting/views.py is now imported — `LeaderboardEntry` migration must be applied before it works

### Migration state
18 migrations exist. There is a merge migration `0018_merge_20260621_1812.py` suggesting the friend's branch was partially merged. After resolving file conflicts, run:
```bash
python manage.py migrate
```

---

## 7. Remaining Problems to Fix

### Priority 1 — Blocking (app won't start/run)
1. Resolve merge conflicts in the 5 template files and `github_scraper.py`
2. Resolve conflict in `core/migrations/0002_company_description...py`
3. Verify `student_leaderboard`, `AIEffectivenessView`, `LeaderboardView` exist in `core/views.py` — if not, create stubs
4. Run `python manage.py migrate` to apply pending migrations

### Priority 2 — Feature completion
5. `company/interview_result.html` is complete but `company_interview_result` view function needs a double-check
6. `templates/company/agent_run_detail.html` — should have a "Generate Interview" button (was pending)
7. Offline interview scheduling form in `applicants.html` — location + contact_person fields may be missing
8. Notification rendering for two interview types (AI vs scheduled) needs distinguishing on dashboard

### Priority 3 — Quality
9. `github_scraper.py` after conflict resolution needs testing — the friend added organization detection and topic scraping which may break if GitHub token is missing
10. `core/migrations/0002` conflict — the friend's version adds fields; need to ensure no column collisions with later migrations

---

## 8. Future Improvements (What Should Be Built Next)

### Short term
- **Resume-to-Profile auto-fill**: When student uploads CV, pre-fill their profile fields (skills, experience, CGPA) — the parser exists, the UI hookup is partial
- **Real-time notifications via WebSocket**: `core/consumers.py` exists and `channels` is now in requirements, but not wired up yet — currently polling every 30s
- **Company analytics dashboard**: Show hiring funnel, conversion rates per weight configuration, agent decision accuracy
- **Student profile completion wizard**: Step-by-step onboarding guide instead of a single long profile page

### Medium term
- **Multi-company application tracking**: Student can see all companies' statuses in one view with a Kanban-style board
- **Scheduled interview slot booking by student**: Slot availability API exists but student-facing booking UI is not built
- **Batch agent run**: Company can run the recruitment agent on all unreviewed applicants with one click
- **Interview recording/transcription**: Currently text-based answers only; voice answer support via WebRTC

### Long term
- **Bias detection layer**: Audit RL weights for demographic bias over time — flag if weights diverge from fair hiring patterns
- **Cross-company skill benchmarking**: Show students how their profile compares to peers who got hired at similar companies
- **API for university integration**: Let universities embed the student portal in their own LMS
- **Mobile app (Flutter)**: The backend is already API-first; a Flutter frontend would be straightforward

---

## 9. What the Developer (Samir) Wants

Based on the full session history, Samir's goals are:

1. **Academic poster** — A research-quality poster documenting the system for submission/presentation. Three versions built: HTML/CSS (web), PowerPoint (3ft×4ft print), and matplotlib chart for the RL weights visualization. All are in the `poster/` folder.

2. **A fully functional platform** — The system should work end-to-end: student applies → agent runs → vetting test sent → AI interview generated → company hires → RL weights update. Every step must work without manual intervention.

3. **Clean, professional UI** — Dark-themed, modern design throughout. No raw Django forms. Custom modals, animated transitions, real-time feedback.

4. **AI that actually learns** — The RL weight system is the core research contribution. Hire/reject signals must update weights correctly and the visualization (ai_agent.html) must show the learning curve clearly.

5. **Merge conflicts resolved** — The friend's additions (leaderboard, hire-readiness scoring, award_points, organization detection in GitHub) should be merged cleanly, not overwritten.

---

## 10. How to Run the Project

```bash
# 1. Activate virtualenv
cd E:\web\ai-talent-match3\Ai_telent_match
.\env\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run migrations
python manage.py migrate

# 4. Start server
python manage.py runserver

# 5. (Optional) Generate the RL weights chart for poster
python poster/rl_weights.py
```

**Environment variables needed (in settings.py or .env):**
- `GEMINI_API_KEY` — Google Gemini API key
- `GITHUB_TOKEN` — GitHub personal access token (for higher rate limits)
- `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` — SMTP config
- `DATABASE_URL` or individual `DATABASES` settings pointing to PostgreSQL

---

## 11. Key File Quick Reference

| Task | File |
|---|---|
| Change matching weights logic | `core/utils/ai_engine.py` |
| Change RL update formula | `core/utils/ai_engine.py` → `update_weights_from_signal()` |
| Change agent steps | `core/utils/recruitment_agent.py` |
| Change interview question prompt | `core/utils/interview_generator.py` |
| Add a new model field | `core/models.py` → then `makemigrations` |
| Add a new API route | `core/urls.py` |
| Add a new page route | `Ai_telent_match/urls.py` |
| Change student dashboard | `templates/student/dashboard.html` |
| Change company applicants page | `templates/company/applicants.html` |
| Change notifications | `core/views.py` → `NotificationsView` |
| Award points to student | `core/utils/points.py` → `award_points(student, 'action')` |

---

*This document reflects the state of the project as understood from the full development session. It should be updated whenever major features are added or the architecture changes.*

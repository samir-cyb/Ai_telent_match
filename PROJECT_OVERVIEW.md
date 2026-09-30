# AI Talent Match — Full Project Reference
> Share this file with any chat to give it complete context of the system.

---

## 1. What This System Does

AI Talent Match is a web-based recruitment platform built with Django 4.2.
Companies post jobs. Candidates create profiles and apply.
The system automatically scores and ranks every candidate for every job.

It solves three problems that existing tools (like LinkedIn, Handshake) do not solve:
- Keyword-only matching misses candidates who have related but differently-named skills
- No tool checks whether a candidate profile is honest
- No tool adapts its scoring formula per company

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Backend Framework | Django 4.2 (Python) |
| Database | PostgreSQL |
| Frontend | Django Templates + Bootstrap |
| LLM (grading, parsing, interview) | Google Gemini API |
| CV/LinkedIn Parsing | LLM-based extraction (resume_parser.py, linkedin_parser.py) |
| Code Sandbox | Isolated subprocess execution (code_executor.py) |
| Reinforcement Learning | Custom Q-learning (inside ai_engine.py) |
| Real-time (WebSocket) | Django Channels + Redis |
| GitHub Data | Custom scraper (github_scraper.py) |

---

## 3. Three Types of Users

| User | What they can do |
|---|---|
| Candidate (Student) | Register, upload CV, add skills/projects, apply for jobs, take tests |
| Company (Employer) | Post jobs, view ranked shortlist, give hire/reject feedback |
| Admin | Review flagged profiles, manage the platform |

---

## 4. How the 5-Stage Pipeline Works

Every time a candidate applies, the system runs these 5 stages in order:

### Stage 1 — Fraud Detection
File: `core/utils/fraud_detector.py`

Runs 8 rules on the candidate profile:
- R1: CGPA ≥ 3.8 but zero projects listed
- R2: Claims expert-level skill but no skill test on record
- R3: GitHub URL listed but commit count = 0
- R4: Profile edited rapidly just before application deadline
- R5: Employment dates overlap between two different jobs
- R6: Applied to too many jobs in 24 hours (spam pattern)
- R7: CGPA is far above the institution average
- R8: CGPA on uploaded transcript differs from CGPA entered on profile

Each triggered rule reduces the trust score τ ∈ [0, 1].
If τ < 0.30 → profile is held for admin review, removed from auto-ranking.

### Stage 2 — Semantic Skill Matching
File: `core/utils/ai_engine.py` (inside AIMatchingEngine class)

Compares candidate skills against job requirements using a curated ontology.
- Direct match → score += 0.8
- Group match (same technology family via ontology) → score += 0.4
- Zero direct matches → final score = 0 (hard domain gate)

Example: Job requires Tableau. Candidate knows Power BI.
Both are in the "data visualization" ontology group → group match = 0.4.

The ontology is defined in `ai_engine.py` as `PROJECT_TECH_IMPLIES` dict.
It covers: Mobile, Frontend, Backend, Data/ML, DevOps, Business, Design, HR domains.

### Stage 3 — Score Calculation
File: `core/utils/ai_engine.py`

Final score formula:
  S = 100 × (w_skill × s_skill + w_cgpa × s_cgpa + w_proj × s_proj + w_act × s_act + w_trust × s_trust)

All weights sum to 1. Each component score is between 0 and 1.

Default weights by department:
- Tech:        skills=0.42, cgpa=0.15, projects=0.25, activity=0.06, trust=0.12
- Business:    skills=0.25, cgpa=0.22, projects=0.10, activity=0.18, trust=0.25
- Design:      skills=0.20, cgpa=0.10, projects=0.42, activity=0.12, trust=0.16
- Engineering: skills=0.37, cgpa=0.25, projects=0.22, activity=0.04, trust=0.12
- Science:     skills=0.30, cgpa=0.33, projects=0.20, activity=0.03, trust=0.14
- Humanities:  skills=0.20, cgpa=0.22, projects=0.10, activity=0.25, trust=0.23

Recruiters see each component score separately on the dashboard.

### Stage 4 — Automated Skill Test (Optional)
Files: `vetting/services/code_executor.py`, `vetting/services/code_grader.py`,
       `vetting/services/question_generator.py`

- For tech roles: candidate submits code → runs in isolated sandbox → LLM grades it
- For non-tech roles: candidate answers MCQ/written questions → LLM grades answers
- OS-level screen lock is active during the test (tab-switching is logged)
- Company can run the test before or after shortlisting
- Grading time: ~335ms per submission
- Achieved binary F1 = 1.000 in testing (zero grading errors on correct/wrong)

### Stage 5 — RL Weight Update
File: `core/utils/ai_engine.py` (Q-learning update method)

Runs after every hire or reject decision.
Update formula: w_i ← w_i + α × o × (s_i − s̄_i)
- α = 0.05 (learning rate — small so weights do not shift too fast)
- o = +1 for hire, −1 for reject
- s_i = candidate's score on dimension i
- s̄_i = running average score on dimension i for that company

After update: each weight clipped to [0.05, 0.60], then re-normalized to sum to 1.
Each company develops its own unique weight profile over time.

---

## 5. Key Source Files

### Core Application — `Ai_telent_match/core/`

| File | What it does |
|---|---|
| `models.py` | All database models: Student, Company, Job, Application, Skill, Project, FraudFlag, AIFeedbackLog, etc. |
| `views.py` | All web views: login, dashboard, job posting, application, shortlist, hire/reject |
| `urls.py` | URL routing for all core views |
| `utils/ai_engine.py` | **Main AI engine**: scoring formula, skill ontology, RL weight update, department weights |
| `utils/fraud_detector.py` | **Fraud detection**: all 8 rules, trust score calculation, FraudFlag creation |
| `utils/resume_parser.py` | Parses uploaded PDF CVs using LLM to extract skills, CGPA, projects |
| `utils/linkedin_parser.py` | Parses LinkedIn profile URL to extract additional skills and experience |
| `utils/llm_client.py` | Wrapper for Gemini API calls used across the system |
| `utils/github_scraper.py` | Fetches GitHub commit count and repo data for fraud rule R3 |
| `utils/pipeline_engine.py` | Orchestrates the full 5-stage pipeline for a candidate-job pair |
| `utils/interview_generator.py` | Generates AI interview questions per job role |
| `utils/ai_effectiveness.py` | Tracks and logs AI decision effectiveness over time |
| `utils/points.py` | Gamification/leaderboard points system for candidate activity |
| `utils/email_helpers.py` | Email notifications (interview invites, status updates) |
| `admin.py` | Django admin panel configuration for all models |
| `decorators.py` | Auth decorators (company_required, student_required, admin_required) |

### Vetting Application — `Ai_telent_match/vetting/`

| File | What it does |
|---|---|
| `models.py` | Assessment, Question, Submission, VettingSession models |
| `views.py` | Test-taking UI, question display, submission handling |
| `urls.py` | URL routing for vetting/test views |
| `services/code_executor.py` | Runs submitted code in an isolated sandbox subprocess |
| `services/code_grader.py` | Sends code + output to LLM for grading (correct/partial/wrong) |
| `services/question_generator.py` | Generates test questions using LLM based on job requirements |

### Django Project Config — `Ai_telent_match/Ai_telent_match/`

| File | What it does |
|---|---|
| `settings.py` | Database config, installed apps, API keys, media files |
| `urls.py` | Root URL configuration (includes core.urls and vetting.urls) |
| `routing.py` | WebSocket routing for Django Channels |
| `wsgi.py` / `asgi.py` | WSGI/ASGI entry points for deployment |

### Utility Scripts — `Ai_telent_match/` (root level)

| File | What it does |
|---|---|
| `manage.py` | Standard Django management entry point |
| `score_trace.py` | Debug tool to trace exactly how a candidate was scored for a job |
| `visualize_results.py` | Generates charts from test results |
| `diagnose_agent.py` | Debugging tool for the AI agent pipeline |
| `enrich_github_projects.py` | Bulk-fetches GitHub data for all student projects |
| `fix_existing_data.py` | One-time data migration/fix script |
| `poster/rl_weights.py` | RL weight visualization for poster/paper figures |

### Management Commands — `core/management/commands/`

| File | What it does |
|---|---|
| `create_test_data.py` | Creates the 5 test students + 8 test jobs in the database |
| `daily_matching.py` | Runs the full matching pipeline for all active jobs (scheduled) |
| `run_poster_tests.py` | Runs all tests and collects results for paper/poster |
| `fix_project_techstack.py` | Fixes tech stack tags on existing projects |
| `populate_leaderboard.py` | Recalculates leaderboard points for all students |

---

## 6. Test Files — `system_tests/`

Run all tests from the project root:
```
cd E:\web\ai-talent-match3\Ai_telent_match
python ..\system_tests\<test_file>.py
```

| File | What it tests | Key Result |
|---|---|---|
| `test_1_baseline_compare.py` | Compares AI system vs keyword-only vs CGPA-only ranking on 5 students × 8 jobs. Ground truth: department match + direct skill count. | AI matches keyword on small set; difference shows on large scale |
| `test_2_rl_convergence.py` | Simulates 20 hire/reject decisions for a research company. Records how weights shift each round. | CGPA weight rises; Skills weight drops — adapts to company hiring pattern |
| `test_3_vetting_accuracy.py` | Tests code grader on 20 Python problems: 8 correct, 8 wrong, 4 partial. Scope: Layers 1+2 only (Layer 3 LLM not tested). | F1 computed at runtime (see test output). 3-class accuracy typically 80–90%. |
| `test_4_trust_score.py` | Calculates trust scores for the 5 core test students. | See live test output — stored DB scores are cache; live formula is authoritative |
| `test_5_performance.py` | Measures system speed on SQLite (dev DB). Single pair + concurrent users. | See live test output — timing on SQLite; PostgreSQL may differ |
| `test_6_agent_decision.py` | Tests the AI recruitment agent decision pipeline (8 cases). | See live test output for strict and conservative accuracy |
| `test_7_ablation.py` | Tests 5 configurations (A–E) on 5 students × 8 jobs. Manual GT. | See live test output — small controlled dataset |
| `test_8_full_evaluation.py` | Full ablation on 200 synthetic students × 50 active jobs × 10 companies. 5-factor GT. | See live test output — do not pre-fill these numbers in the paper |
| `test_9_human_evaluation.py` | 3 SIMULATED expert perspectives (scoring functions, not real humans) assess 30 job-candidate sets. | See live test output. Disclose in paper: evaluators are weighted scoring functions. |
| `create_synthetic_dataset.py` | Generates 200 synthetic student profiles + 50 jobs for test_8 | Used by test_8 and test_9 |
| `generate_figures.py` | Generates all paper figures: ablation bar chart, RL convergence line chart | Saves to system_tests/paper/assets/ |
| `fix_rl_figure.py` | Regenerates RL convergence figure with external legend (no overlap) | Run this before compiling the paper |
| `run_all.py` | Runs all tests in sequence and prints a summary | Use for full verification pass |
| `diagnose_test8.py` | Debug tool for test_8 if results look wrong | Use if test_8 gives unexpected numbers |

---

## 7. Paper Files — `system_tests/paper/`

| File | What it is |
|---|---|
| `ai_talent_match_ieee.tex` | Main LaTeX source for the IEEE conference paper |
| `assets/system_architecture.jpg` | Flowchart figure (single-column, Stage 1→5) |
| `assets/fig1_ablation_study.jpg` | Ablation study bar chart (full-width, 3 panels) |
| `assets/fig2_rl_convergence.jpg` | RL weight convergence over 20 rounds (line chart) |

To compile the paper:
1. Run `python fix_rl_figure.py` first (fixes legend overlap in RL figure)
2. Run `pdflatex ai_talent_match_ieee.tex` three times
3. Requires: IEEEtran.cls in same folder, assets/ subfolder with all images

---

## 8. Ablation Study Results (5 Configurations)

⚠️  **Numbers below are PLACEHOLDERS. Run `test_8_full_evaluation.py` to get actual values
and copy the "PAPER NUMBERS" block printed at the end of the test into your LaTeX table.**

| Config | Description | Top-1 | P@3 | NDCG@5 |
|---|---|---|---|---|
| A | CGPA only | — | — | — |
| B | Keyword only | — | — | — |
| C | Skills + CGPA | — | — | — |
| D | Full model, no RL | — | — | — |
| E | Full model + RL | — | — | — |

Expected ordering: A < B < C < D < E for all metrics.
Expected biggest jump: A→B (skill matching unlocks domain relevance).
Expected RL contribution: D→E, typically +1–3pp Top-1 per company (varies by hiring pattern).

---

## 9. How to Run the Full Test Suite

```bash
# Step 1: Create test data (only needed once)
cd E:\web\ai-talent-match3\Ai_telent_match
python manage.py create_test_data

# Step 2: Create synthetic dataset (for test_8)
python ..\system_tests\create_synthetic_dataset.py

# Step 3: Run all tests
python ..\system_tests\run_all.py

# Step 4: Generate figures for paper
python ..\system_tests\generate_figures.py
python ..\system_tests\fix_rl_figure.py
```

---

## 10. Known Limitations

1. No seniority filter — senior candidate scores high on junior role (no overqualification penalty)
2. Skill ontology is manually maintained — new tools must be added by hand
3. Project score only counts explicitly tagged skills — free-text project descriptions are ignored
4. Human evaluation used simulated roles, not real recruiters — inter-rater score is an estimate
5. Cannot detect cheating via external help during tests (future: computer-vision anti-cheat)

---

## 11. Planned Future Work

- Replace hand-crafted ontology with model trained on ESCO + TalentCLEF data
- Add seniority mismatch penalty to scoring formula
- Deploy computer-vision anti-cheat (webcam: tab-switch, gaze, multiple people detection)
- Deploy voice-based AI interview module (fluency + domain vocabulary + response quality)
- Use NLP/LLM to extract skills from project free-text descriptions

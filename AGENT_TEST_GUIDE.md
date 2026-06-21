# Recruitment Agent — Demo Test Guide
## How to show judges the agent is learning and making decisions

---

## Step 0 — Migrate first

```bash
python manage.py migrate
python manage.py runserver
```

---

## Step 1 — Create a Job (as company)

Log in as your company → Post Job.

Fill in:
- Title: `Junior Python Developer`
- Required Skills: `Python`, `Django`
- Min CGPA: `3.0`

---

## Step 2 — Create 3 Test Students (Django shell)

Open terminal:
```bash
python manage.py shell
```

Paste this block:

```python
from core.models import Student, Skill, StudentSkill

# Ensure skills exist
python_skill, _ = Skill.objects.get_or_create(name='Python', defaults={'category': 'Backend'})
django_skill, _ = Skill.objects.get_or_create(name='Django', defaults={'category': 'Backend'})
react_skill,  _ = Skill.objects.get_or_create(name='React',  defaults={'category': 'Frontend'})

# --- Student A: STRONG candidate ---
a = Student(
    email='student_a@test.com', name='Alice Strong',
    department='CSE', cgpa=3.8, github_score=75, linkedin_score=80,
    activity_score=70, trust_score=65,
)
a.set_password('test123')
a.save()
StudentSkill.objects.get_or_create(student=a, skill=python_skill, defaults={'proficiency_level':'Expert'})
StudentSkill.objects.get_or_create(student=a, skill=django_skill, defaults={'proficiency_level':'Intermediate'})
# Add 4 projects
from core.models import Project
for i in range(4):
    Project.objects.get_or_create(student=a, title=f'Project {i+1}', defaults={'description':'Demo'})

# --- Student B: BORDERLINE candidate ---
b = Student(
    email='student_b@test.com', name='Bob Average',
    department='SWE', cgpa=3.1, github_score=30, linkedin_score=45,
    activity_score=35, trust_score=40,
)
b.set_password('test123')
b.save()
StudentSkill.objects.get_or_create(student=b, skill=python_skill, defaults={'proficiency_level':'Beginner'})
Project.objects.get_or_create(student=b, title='Solo Project', defaults={'description':'Demo'})

# --- Student C: WEAK candidate ---
c = Student(
    email='student_c@test.com', name='Charlie Weak',
    department='BBA', cgpa=2.5, github_score=0, linkedin_score=20,
    activity_score=10, trust_score=15,
)
c.set_password('test123')
c.save()
# No skills, no projects

print("✅ 3 students created:", a.id, b.id, c.id)
```

---

## Step 3 — Apply All 3 Students to Your Job

```python
from core.models import Application, Job, Student
from core.utils.ai_engine import AIMatchingEngine

job = Job.objects.filter(title='Junior Python Developer').first()
a   = Student.objects.get(email='student_a@test.com')
b   = Student.objects.get(email='student_b@test.com')
c   = Student.objects.get(email='student_c@test.com')

for student in [a, b, c]:
    engine = AIMatchingEngine(company=job.company, job=job)
    score, _  = engine.calculate_match(student, job, save_explanation=True)
    Application.objects.get_or_create(
        student=student, job=job,
        defaults={'match_score': score, 'status': 'applied'}
    )
    print(f"{student.name}: match_score = {score:.1f}%")
```

---

## Step 4 — Run the Agent on All 3 Applications

```python
from core.models import Application, Job
from core.utils.recruitment_agent import RecruitmentAgent

job  = Job.objects.filter(title='Junior Python Developer').first()
apps = Application.objects.filter(job=job)

for app in apps:
    agent = RecruitmentAgent(company=job.company)
    run   = agent.run(app, triggered_by='manual')
    print(f"\n{'='*50}")
    print(f"Candidate : {app.student.name}")
    print(f"Score     : {run.score*100:.1f}%")
    print(f"Decision  : {run.decision.upper()}  ({run.confidence} confidence)")
    print(f"Report URL: /company/agent-run/{run.id}/")
    for step in run.reasoning_steps:
        print(f"  Step {step['step']}: {step['action']} → {step['result'][:80]}")
```

### Expected output:
```
Alice Strong  → SHORTLIST  (HIGH confidence)  ~73–78%
Bob Average   → REVIEW     (LOW confidence)   ~52–57%
Charlie Weak  → REJECT     (HIGH confidence)  ~18–25%
```

---

## Step 5 — Show the Difference (BEFORE state is saved)

Open the browser at:
```
http://127.0.0.1:8000/company/applicants/
```

You'll see:
- Alice → green **✓ AGENT: SHORTLIST** badge
- Bob   → yellow **⚠ AGENT: REVIEW** badge
- Charlie → red **✗ AGENT: REJECT** badge

Click **Report** on any badge → full 7-step thought log + fit report.

---

## Step 6 — Change the Weights, Re-run, Show the Difference

### 6a. Change weights via the AI Agent page
Go to `http://127.0.0.1:8000/company/ai-agent/`
→ Click "Edit Weights" → move **CGPA** slider UP to 40%, move **Skills** DOWN to 25% → Save.

### 6b. Re-run the agent on Bob (borderline student)

```python
from core.models import Application, Job
from core.utils.recruitment_agent import RecruitmentAgent

job = Job.objects.filter(title='Junior Python Developer').first()
app = Application.objects.get(student__email='student_b@test.com', job=job)

agent = RecruitmentAgent(company=job.company)
run2  = agent.run(app, triggered_by='manual')
print(f"NEW Decision: {run2.decision.upper()} — Score: {run2.score*100:.1f}%")
print(f"Compare at: /company/agent-run/{run2.id}/")
```

### 6c. Open the report page

Go to `/company/agent-run/<run2_id>/`

You'll see the **"Run History — Before / After Comparison"** table at the bottom showing:
- Run 1: weights (Skills 40%, CGPA 20%) → score X%
- Run 2: weights (Skills 25%, CGPA 40%) → score Y%  **← agent learned from your edit**

Bob's score changes because CGPA weight went up (his CGPA 3.1 is still decent) but skills weight went down (he only has Python, not Django).

---

## Step 7 — Hire Alice, verify RL signal fires

In the applicants page → find Alice → click **Hire**.

Then open:
```
http://127.0.0.1:8000/company/ai-agent/
```

You'll see:
- A new event in the **Agent Event Log**: type = HIRE, reward = +1.0
- The weight evolution chart shows a small update toward Alice's feature profile
- Cumulative reward goes up by 1

This is the **RL Weight Agent + Recruitment Agent working together** — a complete agentic loop.

---

## Files changed in this feature

| File | Change |
|------|--------|
| `core/models.py` | Added `RecruitmentAgentRun` model |
| `core/migrations/0013_recruitment_agent_run.py` | Migration |
| `core/utils/recruitment_agent.py` | 7-step agent logic (NEW) |
| `core/views.py` | Auto-trigger in `ApplyJobView`, `RunRecruitmentAgentView`, `AgentRunsListView`, `AgentRunDetailAPIView`, `company_agent_run_detail`, agent fields in `ApplicationsListView` |
| `core/urls.py` | 3 new API routes |
| `Ai_telent_match/urls.py` | 1 new page route |
| `templates/company/agent_run_detail.html` | Full debug page (NEW) |
| `templates/company/applicants.html` | Agent badge + Run/Re-run button |

"""
Agent Scoring Diagnostic Script
Run: python manage.py shell < diagnose_agent.py
  OR: python manage.py runscript diagnose_agent  (if django-extensions installed)
  OR: python diagnose_agent.py  (from project root with DJANGO_SETTINGS_MODULE set)

Usage: python manage.py shell -c "exec(open('diagnose_agent.py').read())"
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')

from core.models import Student, Job, Application, Company, StudentSkill
from core.utils.recruitment_agent import SKILL_ECOSYSTEM, expand_skill_set
from vetting.models import VettingResult

SEP = "=" * 70

def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

# ── 1. Find all students ──────────────────────────────────────────────────────
section("ALL STUDENTS IN DB")
for s in Student.objects.all():
    skill_objs = StudentSkill.objects.filter(student=s).select_related('skill')
    skill_names = [ss.skill.name for ss in skill_objs]
    print(f"\nStudent : {s.name}  (ID: {s.id})")
    print(f"  CGPA  : {s.cgpa}")
    print(f"  GitHub score : {s.github_score} | activity_score: {s.activity_score}")
    print(f"  linkedin_score: {s.linkedin_score} | trust_score: {s.trust_score}")
    print(f"  Skills in DB ({len(skill_names)}): {skill_names}")

    for ss in skill_objs:
        print(f"    - {ss.skill.name:20s} | {ss.proficiency_level:12s} | cross_validated={ss.cross_validated}")

    print(f"  Projects ({s.projects.count()}):")
    for p in s.projects.prefetch_related('tech_stack').all():
        tech = [t.name for t in p.tech_stack.all()]
        print(f"    [{p.title[:35]:35s}] tech={tech} | dur={p.duration_weeks}wks | "
              f"complexity={p.complexity_score} | github={bool(p.github_url)} | live={bool(p.live_url)}")

    vr_qs = VettingResult.objects.filter(session__student=s).select_related('session__challenge__job__company')
    print(f"  Vetting results ({vr_qs.count()}):")
    for vr in vr_qs:
        ch = vr.session.challenge
        co = ch.job.company.name if ch.job else "?"
        print(f"    [{co}] {ch.title[:40]:40s} tags={ch.skill_tags} score={vr.final_score}")

# ── 2. Find all jobs & companies ──────────────────────────────────────────────
section("ALL JOBS & COMPANIES")
for job in Job.objects.select_related('company').prefetch_related('required_skills').all():
    req = [s.name for s in job.required_skills.all()]
    print(f"\nJob: {job.title} | Company: {job.company.name}")
    print(f"  Required skills: {req}")
    print(f"  Min CGPA: {job.min_cgpa}")
    print(f"  Custom weights: {job.custom_weights}")
    print(f"  Company weights: {job.company.get_weights()}")

# ── 3. Find all applications & recent agent runs ──────────────────────────────
section("ALL APPLICATIONS & AGENT RUNS")
from core.models import RecruitmentAgentRun
for app in Application.objects.select_related('student', 'job__company').all():
    print(f"\nApplication: {app.student.name} → {app.job.title} @ {app.job.company.name}")
    print(f"  Status: {app.status}")
    runs = RecruitmentAgentRun.objects.filter(application=app).order_by('-created_at')
    print(f"  Agent runs: {runs.count()}")
    for run in runs[:3]:
        print(f"    Run {run.id} | score={run.score:.3f} | decision={run.decision} | triggered={run.triggered_by}")

# ── 4. Manual score trace for LATEST agent run ───────────────────────────────
section("MANUAL SCORE TRACE — LATEST RUN")
latest_run = RecruitmentAgentRun.objects.select_related(
    'application__student', 'application__job__company'
).order_by('-created_at').first()

if latest_run:
    app     = latest_run.application
    student = app.student
    job     = app.job
    company = job.company

    print(f"\nTracing: {student.name} → {job.title} @ {company.name}")
    print(f"Score stored in DB: {latest_run.score:.4f} ({latest_run.score*100:.1f}%)")

    req_skills = [s.name.lower() for s in job.required_skills.all()]
    print(f"\nJob required skills: {req_skills}")
    expanded = expand_skill_set(set(req_skills))
    print(f"Expanded skill set ({len(expanded)} items): {sorted(expanded)[:20]}...")

    # Skills in student profile
    skill_objs = StudentSkill.objects.filter(student=student).select_related('skill')
    skill_detail = {ss.skill.name.lower(): ss for ss in skill_objs}
    print(f"\nStudent explicit skills: {list(skill_detail.keys())}")

    # Vetting scores (company-scoped)
    vetting_scores = {}
    for vr in VettingResult.objects.filter(
        session__student=student,
        session__challenge__job__company=company,
    ).select_related('session__challenge'):
        if vr.final_score is None:
            continue
        for tag in (vr.session.challenge.skill_tags or []):
            t = tag.lower()
            sc = float(vr.final_score)
            if t not in vetting_scores or sc > vetting_scores[t]:
                vetting_scores[t] = sc
    print(f"Vetting scores (company-scoped): {vetting_scores}")

    # Project tech_stack implied skills
    implied = {}
    for p in student.projects.prefetch_related('tech_stack').all():
        for tech in p.tech_stack.all():
            t = tech.name.lower()
            implied[t] = implied.get(t, 0) + 1
    print(f"Project-implied skills: {dict(list(implied.items())[:20])}")

    # Per required skill: what score would the agent give?
    print(f"\n--- Skills scoring trace ---")
    SELF_REPORT = {
        ('Expert', True): 0.72, ('Expert', False): 0.60,
        ('Intermediate', True): 0.55, ('Intermediate', False): 0.45,
        ('Beginner', True): 0.35, ('Beginner', False): 0.30,
    }
    for r in req_skills:
        print(f"\n  Required: '{r}'")
        best, best_label = 0.0, 'missing'

        # Direct match
        for cname, ss in skill_detail.items():
            if r not in cname and cname not in r:
                continue
            v = vetting_scores.get(cname)
            if v is not None:
                test_sc = (v/100) if v >= 70 else (v/100)*0.85
                floor   = SELF_REPORT.get((ss.proficiency_level, ss.cross_validated), 0.30) * 0.55
                sc      = max(test_sc, floor)
                lbl     = f"direct+tested({v:.0f}%) → {sc*100:.1f}%"
            else:
                sc  = SELF_REPORT.get((ss.proficiency_level, ss.cross_validated), 0.40)
                lbl = f"direct+self({ss.proficiency_level},cv={ss.cross_validated}) → {sc*100:.1f}%"
            print(f"    Direct match '{cname}': {lbl}")
            if sc > best: best, best_label = sc, lbl

        # Ecosystem match (only if no direct)
        if best == 0:
            children = SKILL_ECOSYSTEM.get(r, [])
            for cname in list(skill_detail.keys()) + list(implied.keys()):
                if cname not in children:
                    continue
                is_implied = cname not in skill_detail
                ss = skill_detail.get(cname)
                v  = vetting_scores.get(cname)
                if v is not None:
                    base = (v/100) if v >= 70 else (v/100)*0.85
                elif is_implied:
                    prof = 'Intermediate' if implied.get(cname, 0) >= 3 else 'Beginner'
                    base = SELF_REPORT.get((prof, False), 0.30) * 0.65
                else:
                    base = SELF_REPORT.get((ss.proficiency_level, ss.cross_validated), 0.40) if ss else 0.30
                eco_sc = round(base * 0.75, 3)
                src = 'implied' if is_implied else 'explicit'
                print(f"    Ecosystem '{cname}' ({src}): {eco_sc*100:.1f}%")
                if eco_sc > best: best, best_label = eco_sc, f"ecosystem via {cname}"

        print(f"  → FINAL score for '{r}': {best*100:.1f}%  ({best_label})")

    # Projects
    print(f"\n--- Projects scoring trace ---")
    for p in student.projects.prefetch_related('tech_stack').all():
        tech = set(t.name.lower() for t in p.tech_stack.all())
        req_set = set(req_skills)
        exp_set = expand_skill_set(req_set)
        direct_ov = len(tech & req_set) / max(len(req_set), 1)
        eco_ov    = len(tech & exp_set) / max(len(exp_set), 1)
        tech_ov   = max(direct_ov, eco_ov * 0.80)
        text      = (p.title + ' ' + p.description).lower()
        text_hits = sum(1 for r in exp_set if r in text)
        text_sc   = min(text_hits / max(len(req_set), 1), 1.0)
        relevance = tech_ov * 0.60 + text_sc * 0.40
        print(f"  [{p.title[:30]:30s}] tech={list(tech)[:4]} | direct_ov={direct_ov:.2f} eco_ov={eco_ov:.2f} "
              f"text_hits={text_hits} | relevance={relevance*100:.0f}%")

    # Weights
    print(f"\n--- Weights ---")
    weights = company.get_weights()
    if job.custom_weights:
        weights = {**weights, **job.custom_weights}
    total_w = sum(weights.values())
    weights = {k: v/total_w for k, v in weights.items()}
    print(f"  Normalized weights: { {k: f'{v*100:.1f}%' for k,v in weights.items()} }")

print(f"\n{SEP}")
print("  DIAGNOSIS COMPLETE")
print(SEP)

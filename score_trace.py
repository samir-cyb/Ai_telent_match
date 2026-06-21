"""
Detailed score trace — uses EXACT same formulas as recruitment_agent.py.
Run: python manage.py shell -c "exec(open('score_trace.py').read())"
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')

from core.models import RecruitmentAgentRun, StudentSkill
from core.utils.recruitment_agent import SKILL_ECOSYSTEM, expand_skill_set
from vetting.models import VettingResult

SELF_REPORT_SCORES = {
    ('Expert',       True):  0.72,
    ('Expert',       False): 0.60,
    ('Intermediate', True):  0.55,
    ('Intermediate', False): 0.45,
    ('Beginner',     True):  0.35,
    ('Beginner',     False): 0.30,
}

SEP = "=" * 60

run = RecruitmentAgentRun.objects.select_related(
    'application__student', 'application__job__company'
).order_by('-created_at').first()

app     = run.application
student = app.student
job     = app.job
company = job.company

print(f"\n{SEP}")
print(f"  Score Trace: {student.name} → {job.title}")
print(f"  Stored score: {run.score*100:.1f}%")
print(SEP)

# ── Weights ────────────────────────────────────────────────────────
weights = dict(company.get_weights())
if job.custom_weights:
    weights.update(job.custom_weights)
total_w = sum(weights.values())
norm_w  = {k: round(v/total_w, 6) for k, v in weights.items()}
print("\nNormalized weights:")
for k, v in norm_w.items():
    print(f"  {k:20s}: {v*100:.1f}%")

# ── Step 1: Skills ─────────────────────────────────────────────────
print(f"\n{SEP}")
print("  SKILLS SCORE  (same formula as agent)")
print(SEP)

req_skills = [s.name.lower() for s in job.required_skills.all()]
print(f"Job required skills: {req_skills}")

skill_objs = StudentSkill.objects.filter(student=student).select_related('skill')
skill_detail = {
    ss.skill.name.lower(): {
        'proficiency':     ss.proficiency_level,
        'cross_validated': ss.cross_validated,
        'vetting_score':   None,
    }
    for ss in skill_objs
}

# Vetting scores (company-scoped)
for vr in VettingResult.objects.filter(
        session__student=student,
        session__challenge__job__company=company,
).select_related('session__challenge'):
    if vr.final_score is None:
        continue
    for tag in (vr.session.challenge.skill_tags or []):
        t = tag.lower()
        if t in skill_detail:
            skill_detail[t]['vetting_score'] = float(vr.final_score)

# Project-implied skills
projects = list(student.projects.prefetch_related('tech_stack').all())
implied_counts = {}
for p in projects:
    for tech in p.tech_stack.all():
        t = tech.name.lower()
        implied_counts[t] = implied_counts.get(t, 0) + 1

for tech, count in implied_counts.items():
    if tech not in skill_detail:
        skill_detail[tech] = {
            'proficiency':     'Intermediate' if count >= 3 else 'Beginner',
            'cross_validated': False,
            'vetting_score':   None,
            'implied':         True,
        }

cand_names = list(skill_detail.keys())
total_skill_score = 0.0

for r in req_skills:
    best = 0.0
    best_label = 'missing'
    for cname in cand_names:
        if r not in cname and cname not in r:
            continue
        info    = skill_detail[cname]
        implied = info.get('implied', False)
        v_score = info.get('vetting_score')
        if v_score is not None:
            raw  = v_score / 100.0
            sc   = raw if v_score >= 70 else raw * 0.85
            key  = (info['proficiency'], info.get('cross_validated', False))
            sc   = max(sc, SELF_REPORT_SCORES.get(key, 0.30) * 0.55)
            lbl  = f"tested({v_score:.0f}%)"
        elif implied:
            key = (info['proficiency'], False)
            sc  = SELF_REPORT_SCORES.get(key, 0.30) * 0.65
            lbl = f"proj-implied({info['proficiency']})"
        else:
            key = (info['proficiency'], info['cross_validated'])
            sc  = SELF_REPORT_SCORES.get(key, 0.40)
            lbl = f"self({info['proficiency']}{'cv' if info['cross_validated'] else ''})"
        if sc > best:
            best, best_label = sc, f"{cname}->{lbl}={sc*100:.0f}%"

    if best == 0.0:
        for cname in cand_names:
            children = SKILL_ECOSYSTEM.get(r, [])
            if cname not in children:
                continue
            info    = skill_detail[cname]
            v_score = info.get('vetting_score')
            if v_score is not None:
                raw  = v_score / 100.0
                base = raw if v_score >= 70 else raw * 0.85
            elif info.get('implied'):
                key  = (info['proficiency'], False)
                base = SELF_REPORT_SCORES.get(key, 0.30) * 0.65
            else:
                key  = (info['proficiency'], info['cross_validated'])
                base = SELF_REPORT_SCORES.get(key, 0.40)
            eco_sc = round(base * 0.75, 3)
            if eco_sc > best:
                best, best_label = eco_sc, f"{r}<-via {cname}={eco_sc*100:.0f}%"

    total_skill_score += best
    print(f"  '{r}': {best_label}")

skills_score = total_skill_score / max(len(req_skills), 1)
print(f"\n  -> Skills score: {skills_score*100:.1f}%")
print(f"  -> Skills contribution: {skills_score * norm_w.get('skills', 0.4)*100:.1f}%")

# ── Step 2: CGPA (REAL formula) ───────────────────────────────────
print(f"\n{SEP}")
print("  CGPA SCORE  (real formula: 0.55 base when meeting min)")
print(SEP)
cgpa     = float(student.cgpa or 0)
min_cgpa = float(job.min_cgpa or 0)
if cgpa > 0:
    if min_cgpa > 0:
        if cgpa < min_cgpa:
            cgpa_score = round((cgpa / min_cgpa) * 0.50, 3)
            print(f"  CGPA {cgpa} below minimum {min_cgpa} -> penalty score={cgpa_score*100:.1f}%")
        else:
            above_pct  = (cgpa - min_cgpa) / (4.0 - min_cgpa) if (4.0 - min_cgpa) > 0 else 1.0
            cgpa_score = round(0.55 + 0.45 * above_pct, 3)
            print(f"  CGPA {cgpa}/4.0 (min {min_cgpa}) -> 0.55+0.45x{above_pct:.2f} = {cgpa_score*100:.1f}%")
    else:
        cgpa_score = round(min(cgpa / 4.0, 1.0), 3)
        print(f"  CGPA {cgpa}/4.0 (no minimum) = {cgpa_score*100:.1f}%")
else:
    cgpa_score = 0.45
    print(f"  CGPA not set -> default 45%")
print(f"  -> CGPA contribution: {cgpa_score * norm_w.get('cgpa', 0.2)*100:.1f}%")

# ── Step 3: Projects (REAL formula) ──────────────────────────────
print(f"\n{SEP}")
print("  PROJECTS SCORE  (real: avg_rel*0.45 + count*0.30 + avg_cplx*0.25)")
print(SEP)

req_skill_set  = set(req_skills)
pc             = len(projects)
total_rel      = 0.0
total_cplx     = 0.0
relevant_count = 0
has_resume     = bool(student.resume)

for p in projects:
    tech_names = set(t.name.lower() for t in p.tech_stack.all())
    text       = (p.title + ' ' + (p.description or '')).lower()

    if req_skill_set:
        per_skill = []
        for r in req_skill_set:
            r_children = set(SKILL_ECOSYSTEM.get(r, []))
            if r in tech_names:
                per_skill.append(1.0)
            elif tech_names & r_children:
                per_skill.append(0.70)
            elif r in text or any(c in text for c in r_children if len(c) > 3):
                per_skill.append(0.30)
            else:
                per_skill.append(0.0)
        rel = sum(per_skill) / len(req_skill_set)
    else:
        rel = 0.5
    if rel >= 0.30:
        relevant_count += 1
    total_rel += rel

    weeks = int(p.duration_weeks or 0)
    if   weeks >= 16: dur_c = 0.35
    elif weeks >= 8:  dur_c = 0.25
    elif weeks >= 4:  dur_c = 0.18
    elif weeks >= 2:  dur_c = 0.10
    elif weeks >= 1:  dur_c = 0.05
    else:
        gemini_c = int(getattr(p, 'complexity_score', 1) or 1)
        dur_c    = round((gemini_c - 1) / 4.0 * 0.25, 3)

    tc     = len(tech_names)
    tech_c = min(tc * 0.05, 0.25)

    words  = len(p.description.split()) if p.description else 0
    if   words >= 100: desc_c = 0.20
    elif words >= 50:  desc_c = 0.14
    elif words >= 20:  desc_c = 0.08
    else:              desc_c = 0.02

    pub_c = (0.10 if p.github_url else 0.0) + (0.10 if p.live_url else 0.0)
    if pub_c == 0.0 and has_resume:
        pub_c = 0.05

    cplx = min(dur_c + tech_c + desc_c + pub_c, 1.0)
    if p.verified:
        cplx = min(cplx + 0.05, 1.0)
    total_cplx += cplx

    print(f"  [{p.title[:28]:28s}] rel={rel*100:.0f}% cplx={cplx*100:.0f}%"
          f" (tech={tc} gh={bool(p.github_url)} ver={p.verified})")

avg_rel       = total_rel  / pc if pc > 0 else 0.0
avg_cplx      = total_cplx / pc if pc > 0 else 0.0
count_score   = min(pc / 8.0, 1.0)
projects_score = round(avg_rel * 0.45 + count_score * 0.30 + avg_cplx * 0.25, 3)

print(f"\n  avg_relevance={avg_rel*100:.1f}% | count={pc} (score={count_score*100:.0f}%) | avg_complexity={avg_cplx*100:.1f}%")
print(f"  -> Projects score: {projects_score*100:.1f}%")
print(f"  -> Projects contribution: {projects_score * norm_w.get('projects', 0.2)*100:.1f}%")

# ── Step 4: Activity (REAL formula) ──────────────────────────────
print(f"\n{SEP}")
print("  ACTIVITY SCORE  (real: github*0.6 + activity*0.4)")
print(SEP)
github_norm    = min(float(student.github_score or 0) / 100, 1.0)
activity_raw   = float(student.activity_score or 0)
activity_score = round(github_norm * 0.6 + min(activity_raw / 100, 1.0) * 0.4, 3)
print(f"  github_score={student.github_score} | activity_score={activity_raw:.0f}")
print(f"  {student.github_score}*0.6 + {activity_raw:.0f}*0.4 = {activity_score*100:.1f}%")
print(f"  -> Activity contribution: {activity_score * norm_w.get('activity', 0.1)*100:.1f}%")

# ── Step 5: Trust (REAL formula) ─────────────────────────────────
print(f"\n{SEP}")
print("  TRUST SCORE  (real: linkedin*0.5 + trust*0.5)")
print(SEP)
linkedin_norm = min(float(student.linkedin_score or 0) / 100, 1.0)
trust_raw     = float(student.trust_score or 0)
trust_score   = round(linkedin_norm * 0.5 + min(trust_raw / 100, 1.0) * 0.5, 3)
print(f"  linkedin_score={student.linkedin_score} | trust_score={trust_raw:.0f}")
print(f"  {student.linkedin_score}*0.5 + {trust_raw:.0f}*0.5 = {trust_score*100:.1f}%")
print(f"  -> Trust contribution: {trust_score * norm_w.get('trust', 0.1)*100:.1f}%")
if (student.linkedin_score or 0) == 0:
    potential_gain = (0.5) * norm_w.get('trust', 0.1)
    print(f"  WARNING: LinkedIn not uploaded! Uploading could add +{potential_gain*100:.1f}% to total score")

# ── Final breakdown ───────────────────────────────────────────────
print(f"\n{SEP}")
print("  FINAL SCORE BREAKDOWN")
print(SEP)
components = {
    'skills':   skills_score,
    'cgpa':     cgpa_score,
    'projects': projects_score,
    'activity': activity_score,
    'trust':    trust_score,
}
total = 0.0
for key, val in components.items():
    w   = norm_w.get(key, 0)
    con = val * w
    total += con
    print(f"  {key:10s}: {val*100:.1f}% x {w*100:.1f}% = {con*100:.2f}%")

print(f"\n  CALCULATED TOTAL: {total*100:.1f}%")
print(f"  STORED IN DB:     {run.score*100:.1f}%")
diff = (total - run.score) * 100
print(f"  DIFFERENCE:       {diff:+.1f}%  (should be near 0 now)")
print(SEP)

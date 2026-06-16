"""
Two-part fix script:
  1. Fill remaining empty tech_stacks (with updated keywords)
  2. Smart proficiency upgrade: infer Expert/Intermediate from project count + experience

Run: python manage.py shell -c "exec(open('fix_and_upgrade.py').read())"
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')

from core.models import Student, StudentSkill, Project, Skill, WorkExperience
from core.views import _infer_tech_from_text

TARGET_EMAIL = 'redwan.ahamad.cse@ulab.edu.bd'   # active account
SEP = "=" * 60

# ─────────────────────────────────────────────────────────────────
# STEP 1 — Fix remaining empty tech_stacks
# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  STEP 1: Fix remaining empty tech_stacks")
print(SEP)

student = Student.objects.filter(email=TARGET_EMAIL).first()
if not student:
    print("Student not found!")
    exit()

print(f"Student: {student.name}  (ID: {student.id})")

fixed = 0
for project in student.projects.prefetch_related('tech_stack').all():
    existing = list(project.tech_stack.values_list('name', flat=True))
    if existing:
        print(f"  SKIP '{project.title[:40]}' — has: {existing}")
        continue

    inferred = _infer_tech_from_text(project.title, project.description or '')
    if not inferred:
        print(f"  EMPTY '{project.title[:40]}' — cannot infer (generic title)")
        continue

    for tech_name in inferred:
        tech_clean = tech_name.strip().lower()
        skill = Skill.objects.filter(name__iexact=tech_clean).first()
        if not skill:
            skill = Skill.objects.create(name=tech_clean, category='Uncategorized')
        project.tech_stack.add(skill)

    print(f"  FIXED '{project.title[:40]}' → {inferred}")
    fixed += 1

print(f"\nFixed {fixed} more projects")

# ─────────────────────────────────────────────────────────────────
# STEP 2 — Smart proficiency upgrade
# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  STEP 2: Smart proficiency upgrade")
print(SEP)
print("Logic:")
print("  - Skill in 3+ projects → Intermediate (min)")
print("  - Skill in 5+ projects → Expert (min)")
print("  - If student has any WorkExperience + skill in 2+ projects → Intermediate")
print("  - Core ML/DL skills (python, tensorflow, pytorch) with ML internship → Expert")

# Count projects per tech skill
tech_project_count = {}
for proj in student.projects.prefetch_related('tech_stack').all():
    for tech in proj.tech_stack.all():
        t = tech.name.lower()
        tech_project_count[t] = tech_project_count.get(t, 0) + 1

print(f"\nTech → project count: {dict(sorted(tech_project_count.items(), key=lambda x: -x[1]))}")

# Check if student has work experience
has_experience = False
try:
    exp_count = WorkExperience.objects.filter(student=student).count()
    has_experience = exp_count > 0
    print(f"Work experiences in DB: {exp_count}")
except Exception:
    print("WorkExperience model not found, checking linkedin/resume data...")
    has_experience = bool(student.linkedin_parsed_data) or bool(student.resume)

# Core ML skills — upgrade aggressively if they have experience + ML projects
ML_CORE = {'python', 'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'sklearn',
           'numpy', 'pandas', 'opencv', 'nlp', 'deep learning', 'machine learning',
           'reinforcementlearning (rl)', 'reinforcementlearning', 'cnns',
           'transfer learning', 'adaptive learning',
           'artificial general intelligence (agi)', 'artificial general intelligence'}

updated = []
skill_objs = StudentSkill.objects.filter(student=student).select_related('skill')

for ss in skill_objs:
    skill_name = ss.skill.name.lower()
    current_level = ss.proficiency_level
    count = tech_project_count.get(skill_name, 0)
    is_ml_core = skill_name in ML_CORE

    # Determine new level
    new_level = current_level  # default: no change

    if is_ml_core and has_experience and count >= 1:
        # ML core skill + work experience → at least Intermediate, likely Expert
        if count >= 3:
            new_level = 'Expert'
        else:
            new_level = 'Intermediate'
    elif is_ml_core and count >= 2:
        new_level = 'Intermediate'
    elif count >= 5:
        new_level = 'Expert'
    elif count >= 3:
        new_level = 'Intermediate'
    elif count >= 2:
        if current_level == 'Beginner':
            new_level = 'Intermediate'
    elif has_experience and count >= 1 and is_ml_core:
        new_level = 'Intermediate'

    if new_level != current_level:
        ss.proficiency_level = new_level
        ss.save()
        updated.append(f"  {ss.skill.name:30s}: {current_level} → {new_level}  (in {count} projects)")
    else:
        pass  # no change needed

if updated:
    print(f"\nUpdated {len(updated)} skill proficiency levels:")
    for u in updated:
        print(u)
else:
    print("\nNo skills updated (may need work experience data or more projects per skill)")

# ─────────────────────────────────────────────────────────────────
# STEP 3 — Final state report
# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  STEP 3: Final state — skills & projects")
print(SEP)

print("\nSkills after update:")
for ss in StudentSkill.objects.filter(student=student).select_related('skill').order_by('proficiency_level'):
    count = tech_project_count.get(ss.skill.name.lower(), 0)
    print(f"  {ss.skill.name:30s} | {ss.proficiency_level:12s} | in {count} projects | cross_validated={ss.cross_validated}")

print("\nProjects after fix:")
for p in student.projects.prefetch_related('tech_stack').all():
    tech = [t.name for t in p.tech_stack.all()]
    print(f"  [{p.title[:35]:35s}] tech={tech}")

print(f"\n{SEP}")
print("DONE. Now re-run the agent on an application to see new score.")
print(SEP)

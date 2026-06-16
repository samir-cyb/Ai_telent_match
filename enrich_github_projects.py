"""
Enrich existing projects that have github_url set.
Fetches real repo data: languages → tech_stack, complexity_score, verified flag.

Run: python manage.py shell -c "exec(open('enrich_github_projects.py').read())"
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')

from core.models import Project, Skill
from core.utils.github_scraper import GitHubValidator

validator = GitHubValidator()
SEP = "=" * 60

print(f"\n{SEP}")
print("  GITHUB PROJECT ENRICHMENT")
print(SEP)

projects_with_url = Project.objects.filter(
    github_url__isnull=False
).exclude(github_url='').select_related('student').prefetch_related('tech_stack')

print(f"Projects with github_url: {projects_with_url.count()}")

for project in projects_with_url:
    student = project.student
    url = project.github_url.rstrip('/')
    if url.endswith('.git'):
        url = url[:-4]
    parts = url.replace('https://github.com/', '').split('/')
    if len(parts) < 2:
        print(f"\n  SKIP '{project.title}' — invalid URL: {url}")
        continue

    repo_owner, repo_name = parts[0], parts[1]
    print(f"\n  Project: '{project.title}' ({repo_owner}/{repo_name})")

    details = validator.fetch_repository_details(repo_owner, repo_name)
    if not details:
        print(f"    ERROR: Could not fetch repo details")
        continue

    # Update complexity
    new_c = validator.calculate_project_complexity(details)
    old_c = project.complexity_score or 1
    if new_c > old_c:
        project.complexity_score = new_c
        print(f"    Complexity: {old_c} → {new_c}")
    else:
        print(f"    Complexity: {old_c} (no change, GitHub={new_c})")

    # Add languages to tech_stack
    existing = set(t.name.lower() for t in project.tech_stack.all())
    added = []
    for lang in details.get('languages', {}).keys():
        lang_clean = lang.strip().lower()
        if lang_clean and lang_clean not in existing:
            skill = Skill.objects.filter(name__iexact=lang_clean).first()
            if not skill:
                skill = Skill.objects.create(name=lang_clean, category='Uncategorized')
            project.tech_stack.add(skill)
            existing.add(lang_clean)
            added.append(lang_clean)
    if added:
        print(f"    Added to tech_stack: {added}")
    else:
        print(f"    Tech_stack unchanged (existing: {list(existing)})")

    # Verify ownership — normalize underscore/hyphen (samir_cyb == samir-cyb)
    def _norm(s): return s.lower().replace('-', '_').replace(' ', '_')
    student_gh = _norm(student.github_username or '')
    if student_gh and _norm(repo_owner) == student_gh:
        project.verified = True
        print(f"    Verified ✓ (owner matches student's github_username)")

    # Stars / README info
    print(f"    Stars={details.get('stars',0)} | Forks={details.get('forks',0)} | "
          f"Languages={list(details.get('languages',{}).keys())}")

    project.save()

print(f"\n{SEP}")
print("DONE. Re-run the agent to see improved scores.")
print(SEP)

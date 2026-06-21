"""
Quick fix script: patch existing DB data
- Fill empty tech_stack for ML/AI projects
- Optionally upgrade skill proficiency for students with ML/DL internships + research papers

Run: python manage.py shell -c "exec(open('fix_existing_data.py').read())"
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')

from core.models import Project, Skill, Student, StudentSkill

# ── Inference map (same as in views.py) ──────────────────────────────────────
_TITLE_TECH_MAP = [
    # Python AI/ML — unambiguous
    (['rag system', 'retrieval augmented', 'langchain', 'llamaindex', 'vector store', 'embedding'],
     ['python', 'langchain', 'openai', 'faiss']),
    (['large language model', 'llm', ' gpt', 'language model', 'huggingface', 'transformers'],
     ['python', 'openai', 'langchain', 'transformers']),
    (['chatbot', 'medical chatbot', 'health chatbot', 'ai chatbot'],
     ['python', 'nlp', 'tensorflow']),
    (['natural language processing', 'nlp', 'text classification', 'named entity recognition',
      'sentiment analysis', 'text mining'],
     ['python', 'nlp', 'scikit-learn']),
    (['computer vision', 'image detection', 'object detection', 'face recognition', 'yolo'],
     ['python', 'opencv', 'tensorflow']),
    (['deep learning', 'neural network', 'cnn ', 'rnn ', 'lstm', 'convolutional'],
     ['python', 'tensorflow', 'pytorch']),
    (['reinforcement learning', 'marl', 'multi-agent reinforcement', 'rl agent', 'q-learning'],
     ['python', 'pytorch', 'tensorflow']),
    (['machine learning model', 'ml model', 'scikit', 'sklearn', 'xgboost', 'random forest',
      'feature engineering'],
     ['python', 'scikit-learn', 'pandas']),
    (['robotics', 'robotic arm', 'ros ', 'robot operating'],
     ['python', 'ros', 'arduino']),
    (['data analysis', 'data science', 'data pipeline', 'pandas', 'numpy'],
     ['python', 'pandas', 'numpy']),
    # Explicit Python web frameworks
    (['django', 'django rest', 'drf'], ['python', 'django']),
    (['flask app', 'flask api', 'flask web'], ['python', 'flask']),
    (['fastapi', 'fast api'], ['python', 'fastapi']),
    # Mobile
    (['flutter', 'dart '], ['flutter', 'dart']),
    (['react native'], ['javascript', 'react native']),
    (['android', 'kotlin', 'android studio'], ['android', 'kotlin', 'java']),
    (['ios app', 'swift ', 'swiftui'], ['ios', 'swift']),
    # Frontend JS
    (['react.js', 'reactjs', 'react app', 'next.js', 'nextjs'], ['javascript', 'react']),
    (['vue.js', 'vuejs', 'nuxt'], ['javascript', 'vue']),
    (['angular', 'angularjs'], ['javascript', 'typescript', 'angular']),
    # Backend (non-Python)
    (['node.js', 'nodejs', 'express.js', 'expressjs'], ['javascript', 'nodejs']),
    (['spring boot', 'spring mvc'], ['java', 'spring']),
    (['laravel', 'php backend'], ['php', 'laravel']),
    # DB/Infra
    (['firebase', 'firestore'], ['firebase']),
    (['mongodb', 'mongoose'], ['mongodb']),
]

def infer_tech(title, description):
    combined = (title + ' ' + (description or '')).lower()
    result = set()
    for keywords, techs in _TITLE_TECH_MAP:
        if any(kw in combined for kw in keywords):
            result.update(techs)
    return list(result)

# ── Step 1: Fix empty tech_stack for all projects ─────────────────────────────
print("\n" + "="*60)
print("STEP 1: Fixing empty tech_stack on projects")
print("="*60)

fixed = 0
for project in Project.objects.prefetch_related('tech_stack').all():
    existing = list(project.tech_stack.values_list('name', flat=True))
    if existing:
        print(f"  SKIP '{project.title[:40]}' — already has: {existing}")
        continue

    inferred = infer_tech(project.title, project.description or '')
    if not inferred:
        print(f"  SKIP '{project.title[:40]}' — no inference possible")
        continue

    for tech_name in inferred:
        tech_clean = tech_name.strip().lower()
        skill = Skill.objects.filter(name__iexact=tech_clean).first()
        if not skill:
            skill = Skill.objects.create(name=tech_clean, category='Uncategorized')
        project.tech_stack.add(skill)

    print(f"  FIXED '{project.title[:40]}' → {inferred}")
    fixed += 1

print(f"\nFixed {fixed} projects with empty tech_stack")

# ── Step 2: Show current skill proficiency breakdown ──────────────────────────
print("\n" + "="*60)
print("STEP 2: Current skill proficiency breakdown (before any fix)")
print("="*60)

for student in Student.objects.all():
    ss_qs = StudentSkill.objects.filter(student=student).select_related('skill')
    levels = {}
    for ss in ss_qs:
        levels.setdefault(ss.proficiency_level, []).append(ss.skill.name)

    print(f"\nStudent: {student.name}")
    for lvl, skills in levels.items():
        print(f"  {lvl}: {skills}")

print("\n" + "="*60)
print("DONE. Now re-run the agent to see improved scores.")
print("="*60)
print("""
ACTION NEEDED — Proficiency levels are still all 'Beginner'.
To fix this, go to your Profile page and manually update:
  - Python → Expert  (you have internship + research papers)
  - TensorFlow → Expert
  - PyTorch → Expert
  - Machine Learning → Expert
  - Deep Learning → Expert
  - NLP → Intermediate
  - LangChain → Intermediate
  - OpenCV → Intermediate

OR re-upload your CV — the parser prompt has been improved to
detect Expert/Intermediate from context (internship, research papers).
""")
